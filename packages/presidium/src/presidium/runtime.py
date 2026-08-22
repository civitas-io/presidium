"""GovernedRuntime — governance-wrapped Civitas runtime."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from civitas import Runtime
from civitas.plugins.model import ModelProvider
from civitas.plugins.tools import ToolProvider
from civitas.process import AgentProcess
from civitas.secrets.substitution import substitute_vars
from civitas.security.identity import AgentIdentity

from presidium.approval import ApprovalService, CallbackApprovalProvider
from presidium.audit import AuditSink, InProcessAuditEnricher
from presidium.credentials import CredentialProvider, EnvCredentialProvider
from presidium.model import AgentRecord, EvaluationStage, Grant, PolicyDecision, PolicyRule
from presidium.policy._base import PolicyEngine
from presidium.policy.cel import CelPolicyEngine
from presidium.providers.civitas_adapters import GovernedModelProviderAdapter, GovernedToolAdapter
from presidium.providers.model import GovernedModelProvider
from presidium.providers.tool import GovernedToolProvider
from presidium.registry._base import AgentRegistry
from presidium.registry.memory import InMemoryRegistry

logger = logging.getLogger(__name__)


class GovernedRuntime:
    """Governance layer wrapping a Civitas Runtime.

    Two construction modes:

    1. ``from_config("topology.yaml")`` — reads YAML, extracts the
       ``presidium:`` block, builds governance components, delegates
       the rest to ``Runtime.from_config_dict()``.

    2. Programmatic — pass a pre-built Civitas ``Runtime`` and governance
       components directly.
    """

    def __init__(
        self,
        civitas_runtime: Runtime | None = None,
        *,
        registry: AgentRegistry | None = None,
        engine: PolicyEngine | None = None,
        credentials: CredentialProvider | None = None,
        approval: ApprovalService | None = None,
        audit_sink: AuditSink | None = None,
        key_dir: str | Path | None = None,
    ) -> None:
        self._runtime = civitas_runtime
        self.registry: AgentRegistry = registry or InMemoryRegistry()
        self.engine: PolicyEngine = engine or CelPolicyEngine()
        self.credentials: CredentialProvider = credentials or EnvCredentialProvider()
        self.approval: ApprovalService = approval or CallbackApprovalProvider()

        self.audit_enricher: InProcessAuditEnricher | None = None
        if audit_sink is not None:
            self.audit_enricher = InProcessAuditEnricher(audit_sink, self.registry)

        self.model_provider = GovernedModelProvider(
            engine=self.engine,
            registry=self.registry,
            approval=self.approval,
            audit_sink=self.audit_enricher,
        )

        self.tool_provider = GovernedToolProvider(
            engine=self.engine,
            registry=self.registry,
            approval=self.approval,
            audit_sink=self.audit_enricher,
        )

        self._pending_agents: dict[str, dict[str, Any]] = {}
        self._trust_domain = "local"
        # Default: `.presidium/keys` under the current working directory --
        # mirrors `civitas security init`'s own default layout so operators
        # already familiar with Civitas's key tooling find keys in the
        # expected place. Real per-agent Ed25519 keypairs are provisioned
        # lazily in `start()` via `AgentIdentity.load_or_generate()`, not
        # eagerly here (agent names aren't known until `_pending_agents` is
        # populated by `from_config()` or set directly by a caller).
        self._key_dir = Path(key_dir) if key_dir is not None else Path(".presidium/keys")

    @classmethod
    def from_config(
        cls,
        path: str | Path,
        agent_classes: dict[str, type[AgentProcess]] | None = None,
    ) -> GovernedRuntime:
        """Build a GovernedRuntime from a topology YAML file.

        Reads the full YAML, extracts the ``presidium:`` block, passes
        the rest to ``Runtime.from_config_dict()``, and builds governance
        components from the presidium config.
        """
        full_config = yaml.safe_load(Path(path).read_text())
        full_config = substitute_vars(full_config)

        presidium_config = full_config.pop("presidium", {})

        civitas_runtime = Runtime.from_config_dict(full_config, agent_classes)

        registry_cfg = presidium_config.get("registry", {})
        trust_domain = registry_cfg.get("trust_domain", "local")
        key_dir = registry_cfg.get("key_dir")

        policies_cfg = presidium_config.get("policies", [])
        rules = _parse_policy_rules(policies_cfg)
        engine = CelPolicyEngine()
        if rules:
            engine.load_policies(rules)

        governed = cls(
            civitas_runtime=civitas_runtime,
            registry=InMemoryRegistry(),
            engine=engine,
            key_dir=key_dir,
        )
        governed._trust_domain = trust_domain

        agents_cfg = presidium_config.get("agents", {})
        governed._pending_agents = agents_cfg

        return governed

    async def start(self) -> None:
        for agent_name, agent_cfg in self._pending_agents.items():
            grants = [
                Grant(
                    resources=g.get("resources", []),
                    actions=g.get("actions", []),
                    scope=g.get("scope", {}),
                    condition=g.get("condition"),
                )
                for g in agent_cfg.get("grants", [])
            ]
            # Real Ed25519 identity binding (2026-08-22 fix -- previously
            # hardcoded to "", see docs/vision/roadmap.md's Implementation
            # Priority section). `load_or_generate` persists the keypair to
            # `{key_dir}/{agent_name}/id_ed25519{,.pub}` on first use and
            # loads the same one on every subsequent start -- an agent's
            # identity survives restarts, matching AgentRecord's own
            # documented "persistent identity" contract.
            identity = AgentIdentity.load_or_generate(agent_name, self._key_dir)
            record = AgentRecord(
                agent_id=f"presidium://{self._trust_domain}/{agent_name}",
                name=agent_name,
                public_key=identity.public_key_b64(),
                owner=agent_cfg.get("owner"),
                grants=grants,
            )
            await self.registry.register(record)

        if self._runtime is not None:
            await self._runtime.start()

    def reload_policies(self, path: str | Path) -> int:
        """Hot-reload policies from a YAML file without restarting the runtime.

        Parses the ``presidium.policies`` block and atomically replaces the
        compiled rules in the policy engine. Returns the number of rules loaded.
        """
        full_config = yaml.safe_load(Path(path).read_text())
        full_config = substitute_vars(full_config)
        presidium_config = full_config.get("presidium", {})
        policies_cfg = presidium_config.get("policies", [])
        rules = _parse_policy_rules(policies_cfg)
        self.engine.load_policies(rules)
        logger.info("policy.reload rules=%d source=%s", len(rules), path)
        return len(rules)

    async def stop(self) -> None:
        if self._runtime is not None:
            await self._runtime.stop()

    async def ask(self, agent_name: str, payload: dict[str, Any], **kwargs: Any) -> Any:
        if self._runtime is None:
            raise RuntimeError("No Civitas runtime configured")
        return await self._runtime.ask(agent_name, payload, **kwargs)

    async def send(self, agent_name: str, payload: dict[str, Any], **kwargs: Any) -> None:
        if self._runtime is None:
            raise RuntimeError("No Civitas runtime configured")
        await self._runtime.send(agent_name, payload, **kwargs)

    def model_for(self, agent_name: str, backend: ModelProvider) -> GovernedModelProviderAdapter:
        """Wrap a real civitas ModelProvider with policy enforcement, bound to
        one agent. Mirrors civitas's own `AgentProcess.model_for()` naming
        convention directly. Assign the result to that agent's own `self.llm`
        (e.g. in its `on_start()`) to make its LLM calls governed,
        transparently -- Civitas itself has no concept of governance;
        Presidium is the opinionated layer that adds it, on top of a real
        backend it never replaces.
        """
        return GovernedModelProviderAdapter(
            backend=backend, model_provider=self.model_provider, agent_name=agent_name
        )

    def tool_for(self, agent_name: str, backend: ToolProvider) -> GovernedToolAdapter:
        """Wrap a real civitas ToolProvider (one named tool) with policy
        enforcement, bound to one agent. Register the result into that
        agent's own `self.tools` in place of the real tool directly (the
        same per-agent-construction pattern `civitas.process.AgentProcess.
        connect_mcp()` already uses for civitas-io/fabrica's own MCPTool).
        """
        return GovernedToolAdapter(
            backend=backend, tool_provider=self.tool_provider, agent_name=agent_name
        )


def _parse_policy_rules(configs: list[dict[str, Any]]) -> list[PolicyRule]:
    rules: list[PolicyRule] = []
    for cfg in configs:
        stage_raw = cfg.get("stage", "pre_tool")
        if isinstance(stage_raw, list):
            stage: EvaluationStage | list[EvaluationStage] = [EvaluationStage(s) for s in stage_raw]
        else:
            stage = EvaluationStage(stage_raw)

        approvers_raw = cfg.get("approvers", [])
        rules.append(
            PolicyRule(
                name=cfg["name"],
                stage=stage,
                expression=cfg["expression"],
                decision=PolicyDecision(cfg.get("decision", "deny")),
                reason=cfg.get("reason"),
                priority=cfg.get("priority", 0),
                approvers=tuple(approvers_raw),
                enabled=cfg.get("enabled", True),
            )
        )
    return rules
