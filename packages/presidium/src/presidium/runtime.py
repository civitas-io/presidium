"""GovernedRuntime — governance-wrapped Civitas runtime."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from civitas import Runtime
from civitas.process import AgentProcess
from civitas.secrets.substitution import substitute_vars

from presidium.approval import ApprovalService, CallbackApprovalProvider
from presidium.audit import AuditSink, InProcessAuditEnricher
from presidium.credentials import CredentialProvider, EnvCredentialProvider
from presidium.model import AgentRecord, EvaluationStage, Grant, PolicyDecision, PolicyRule
from presidium.policy._base import PolicyEngine
from presidium.policy.cel import CelPolicyEngine
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

        policies_cfg = presidium_config.get("policies", [])
        rules = _parse_policy_rules(policies_cfg)
        engine = CelPolicyEngine()
        if rules:
            engine.load_policies(rules)

        governed = cls(
            civitas_runtime=civitas_runtime,
            registry=InMemoryRegistry(),
            engine=engine,
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
            record = AgentRecord(
                agent_id=f"presidium://{self._trust_domain}/{agent_name}",
                name=agent_name,
                public_key="",
                owner=agent_cfg.get("owner"),
                grants=grants,
            )
            await self.registry.register(record)

        if self._runtime is not None:
            await self._runtime.start()

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
