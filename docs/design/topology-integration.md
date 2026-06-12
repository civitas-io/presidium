# Design: Topology Integration

> How Presidium governance config is wired into Civitas's topology YAML and runtime startup.

**Status:** Draft (June 2026)
**Package:** `presidium` (GovernedRuntime) / `civitas` (2 minimal changes)
**Milestone:** M2
**Requirements:** [topology-integration-requirements.md](topology-integration-requirements.md)

## Problem Statement

Users configure Civitas via a single topology YAML file. Presidium needs to add governance config to this file and wrap Civitas components during startup. But Civitas rejects unknown top-level YAML keys, and Presidium needs control over the initialization sequence to wrap components before agents start.

## Goals

1. Single YAML file for both runtime and governance configuration
2. GovernedRuntime delegates to Civitas Runtime — no duplication
3. Minimal Civitas changes (2 small, non-breaking additions)
4. Programmatic API for users who build runtimes in code

## Non-Goals (M2)

- CLI integration (`presidium run`) — M5
- Config hot-reload — M3
- Topology validation command — M5

---

## Architecture

```
User's topology.yaml
    ↓
GovernedRuntime.from_config("topology.yaml")
    ↓
    ├── Read full YAML
    ├── substitute_vars() for ${VAR_NAME}
    ├── Extract presidium: block
    ├── Pass remaining config → Runtime.from_config_dict()
    │       ↓
    │       Civitas builds: Supervisor, Transport, Bus, Registry, Plugins
    │       Returns: Runtime (not yet started)
    │
    ├── Build governance components from presidium: block
    │       ├── AgentRegistry
    │       ├── CelPolicyEngine (compile expressions)
    │       ├── CredentialProvider
    │       ├── ApprovalService
    │       └── AuditEnricher
    │
    ├── Register per-agent governance data (owner, grants)
    │
    ├── Wrap Civitas components
    │       ├── ModelProvider → GovernedModelProvider
    │       ├── ToolProvider → GovernedToolProvider
    │       └── AuditSink → AuditEnricher(downstream=original_sink)
    │
    └── Return GovernedRuntime
            ↓
        await governed_runtime.start()
            ↓
        Delegates to civitas_runtime.start()
```

---

## Civitas-Side Changes (2 Changes)

### Change 1: Add `"presidium"` to known config keys

**File:** `civitas/runtime.py` (1-line change)

```python
_KNOWN_CONFIG_KEYS = {
    "transport", "plugins", "supervision", "supervisor", "mcp", "security", "audit",
    "presidium",  # Presidium governance config (ignored by Civitas, read by Presidium)
}
```

Civitas does not parse, validate, or use the `presidium:` block. It simply doesn't reject it.

### Change 2: Add `from_config_dict()` classmethod

**File:** `civitas/runtime.py` (refactor of existing `from_config()`)

```python
@classmethod
def from_config_dict(
    cls,
    config: dict[str, Any],
    agent_classes: dict[str, type[AgentProcess]] | None = None,
) -> Runtime:
    """Build a Runtime from a pre-parsed config dict.
    
    Same as from_config() but accepts a dict instead of a file path.
    Useful when the caller has already parsed and modified the YAML
    (e.g., Presidium extracting the presidium: block before passing
    the rest to Civitas).
    """
    # All the existing from_config() logic, minus the file reading + substitute_vars()
    # The caller is responsible for variable substitution if needed.
    ...

@classmethod
def from_config(
    cls,
    path: str | Path,
    agent_classes: dict[str, type[AgentProcess]] | None = None,
) -> Runtime:
    """Build a Runtime from a YAML topology file."""
    config = yaml.safe_load(Path(path).read_text())
    config = substitute_vars(config)
    return cls.from_config_dict(config, agent_classes)
```

This is a non-breaking refactor — `from_config()` still works exactly as before. `from_config_dict()` is the new public API that Presidium calls.

---

## GovernedRuntime

```python
from __future__ import annotations
from pathlib import Path
from typing import Any

import yaml

from civitas import Runtime
from civitas.secrets.substitution import substitute_vars

class GovernedRuntime:
    """Runtime with Presidium governance.
    
    Wraps a Civitas Runtime, adding policy enforcement, agent registry,
    credential governance, approval service, and audit enrichment.
    
    Usage:
        # From YAML (single file)
        runtime = GovernedRuntime.from_config("topology.yaml")
        await runtime.start()
        
        # Programmatic
        runtime = GovernedRuntime(
            civitas_runtime=Runtime(supervisor=...),
            registry=InMemoryRegistry(),
            policy_engine=CelPolicyEngine(rules=[...]),
        )
        await runtime.start()
    """
    
    def __init__(
        self,
        civitas_runtime: Runtime,
        registry: AgentRegistry | None = None,
        policy_engine: PolicyEngine | None = None,
        credential_provider: CredentialProvider | None = None,
        approval_service: ApprovalService | None = None,
        audit_enricher: AuditEnricher | None = None,
    ) -> None:
        self._runtime = civitas_runtime
        self._registry = registry or InMemoryRegistry()
        self._policy_engine = policy_engine or CelPolicyEngine()
        self._credential_provider = credential_provider or EnvCredentialProvider()
        self._approval_service = approval_service or CallbackApprovalProvider()
        self._audit_enricher = audit_enricher
    
    @classmethod
    def from_config(
        cls,
        path: str | Path,
        agent_classes: dict[str, type] | None = None,
    ) -> GovernedRuntime:
        """Build a GovernedRuntime from a topology YAML file.
        
        Reads the full YAML, extracts the presidium: block, passes
        the rest to Civitas, then builds governance components.
        """
        full_config = yaml.safe_load(Path(path).read_text())
        full_config = substitute_vars(full_config)
        
        # Extract presidium config (Civitas would ignore it anyway)
        presidium_config = full_config.pop("presidium", {})
        
        # Build Civitas runtime from remaining config
        civitas_runtime = Runtime.from_config_dict(full_config, agent_classes)
        
        # Build governance components
        registry = _build_registry(presidium_config.get("registry", {}))
        policy_engine = _build_policy_engine(presidium_config.get("policies", []))
        credential_provider = _build_credential_provider(presidium_config.get("credentials", {}))
        approval_service = _build_approval_service(presidium_config.get("approval", {}))
        audit_enricher = _build_audit_enricher(presidium_config.get("audit", {}), registry)
        
        governed = cls(
            civitas_runtime=civitas_runtime,
            registry=registry,
            policy_engine=policy_engine,
            credential_provider=credential_provider,
            approval_service=approval_service,
            audit_enricher=audit_enricher,
        )
        
        # Register per-agent governance data
        agents_config = presidium_config.get("agents", {})
        governed._pending_agent_config = agents_config
        
        return governed
    
    async def start(self) -> None:
        """Start the governed runtime.
        
        1. Register per-agent governance data (owner, grants)
        2. Wrap Civitas components with governance layers
        3. Delegate to Civitas Runtime.start()
        """
        # Register agents in governance registry
        for agent_name, agent_cfg in self._pending_agent_config.items():
            record = AgentRecord(
                agent_id=f"presidium://{self._trust_domain}/{agent_name}",
                name=agent_name,
                owner=agent_cfg.get("owner"),
                grants=[Grant(**g) for g in agent_cfg.get("grants", [])],
            )
            await self._registry.register(record)
        
        # Wrap Civitas components
        self._wrap_components()
        
        # Start Civitas runtime
        await self._runtime.start()
    
    async def stop(self) -> None:
        await self._runtime.stop()
    
    # Delegate all Runtime methods
    async def ask(self, agent_name, payload, **kwargs):
        return await self._runtime.ask(agent_name, payload, **kwargs)
    
    async def send(self, agent_name, payload, **kwargs):
        return await self._runtime.send(agent_name, payload, **kwargs)
    
    def get_agent(self, name):
        return self._runtime.get_agent(name)
```

---

## Full YAML Example

```yaml
# topology.yaml — single file for runtime + governance

transport:
  type: in_process

plugins:
  models:
    - type: anthropic
      config:
        api_key: ${ANTHROPIC_API_KEY}

supervision:
  name: root
  strategy: ONE_FOR_ONE
  children:
    - agent:
        name: researcher
        type: myapp.ResearchAgent
    - agent:
        name: writer
        type: myapp.WriterAgent

presidium:
  registry:
    backend: sqlite
    db_path: ./presidium.db
    default_trust: 0.5

  policies:
    - name: enforce-grants
      stage: pre_tool
      expression: >
        !agent.grants.exists(g,
          request.resource in g.resources &&
          request.action in g.actions
        )
      decision: deny
      reason: "No grant for this resource/action"
      priority: 100

    - name: trust-gate-writes
      stage: pre_tool
      expression: >
        request.action == "write" && agent.trust.value < 0.7
      decision: require_approval
      reason: "Write actions require approval when trust < 0.7"
      approvers: ["security-team@acme.com"]
      priority: 90

  credentials:
    backend: env

  approval:
    backend: callback
    default_timeout: 300

  audit:
    enrichment: true
    cache_ttl: 5.0

  agents:
    researcher:
      owner: alice@acme.com
      grants:
        - resources: ["tool:web_search"]
          actions: ["invoke"]
        - resources: ["tool:database"]
          actions: ["read"]
        - resources: ["credential:anthropic"]
          actions: ["read"]
    writer:
      owner: bob@acme.com
      grants:
        - resources: ["tool:database"]
          actions: ["read", "write"]
          condition: "agent.trust.value >= 0.7"
        - resources: ["credential:anthropic"]
          actions: ["read"]
```

---

## Startup: Without Governance vs With Governance

### Without Presidium (existing Civitas)
```python
from civitas import Runtime

runtime = Runtime.from_config("topology.yaml")
# presidium: block is ignored (known key, but Civitas doesn't parse it)
await runtime.start()
```

### With Presidium
```python
from presidium import GovernedRuntime

runtime = GovernedRuntime.from_config("topology.yaml")
# presidium: block is parsed, governance components built, Civitas components wrapped
await runtime.start()
```

Same YAML file. Different entry point. Governance is opt-in at the code level.

---

## Civitas Integration Points

| Civitas Component | How Presidium Integrates |
|---|---|
| `_KNOWN_CONFIG_KEYS` | Add `"presidium"` (1-line change) |
| `Runtime.from_config()` | Refactor into `from_config_dict()` + file-loading wrapper |
| `Runtime._model_provider` | Replaced with GovernedModelProvider at startup |
| `Runtime._tool_registry` | Replaced with GovernedToolProvider at startup |
| `Runtime._audit_sink` | Replaced with AuditEnricher(downstream=original_sink) at startup |
| `Runtime.start()` | Called by GovernedRuntime.start() after governance setup |
| `Runtime.stop()` | Called by GovernedRuntime.stop() |

---

## Design Decisions

| # | Decision | Choice | Alternatives Considered | Rationale |
|---|---|---|---|---|
| T1 | Config location | Single YAML, `presidium:` key | Separate file, env vars only | One file = one truth. Users manage one file, not two. |
| T2 | Entry point | GovernedRuntime.from_config() wraps Runtime | Monkey-patch Runtime, subclass Runtime | Wrapper is clean. No inheritance, no patching. Delegation only. |
| T3 | Civitas changes | 2 additions: known key + from_config_dict() | Zero changes (separate file), large changes (plugin system) | Minimal surface. Non-breaking. from_config_dict() is useful independently. |
| T4 | Wrapping timing | Before Runtime.start(), after Runtime construction | During start(), after first message | Components must be wrapped before any agent processes a message. No governance gap. |
| T5 | Opt-in governance | No presidium: block = GovernedRuntime acts like Runtime | Always require governance, error if missing | Governance is additive. Missing config = no governance, not an error. |

---

## Open Questions (Deferred)

1. **CLI integration**: should `civitas run` detect `presidium:` and auto-use GovernedRuntime? (M5)
2. **Config validation CLI**: should `presidium topology validate` check the presidium: block? (M5)
3. **Config hot-reload**: should policy changes be pickable without restart? (M3)
4. **Multi-file support**: should `presidium:` support `!include` for external policy files? (M3)
