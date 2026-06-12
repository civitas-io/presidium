# Topology Integration: Requirements

> How Presidium's governance configuration is wired into Civitas's topology YAML and runtime startup.
> Status: Draft
> Milestone: M2 (Core Interfaces + CEL Policy)

## Overview

Users configure Civitas agent systems via a single topology YAML file. Presidium must integrate into this file seamlessly — one file, one `civitas run` command, governance applied automatically.

The challenge: Civitas validates top-level YAML keys and rejects unknowns. A `presidium:` block in the YAML would be rejected without a small Civitas-side change. Additionally, Presidium needs to wrap Civitas components (ModelProvider → GovernedModelProvider, AuditSink → AuditEnricher) during startup, which requires control over the initialization sequence.

The approach: **Option B + GovernedRuntime wrapper**.
1. Civitas adds `"presidium"` to its known config keys (1-line change — ignores the block)
2. Civitas adds a `from_config_dict()` classmethod (small refactor — accepts pre-parsed dict)
3. Presidium provides `GovernedRuntime.from_config()` that reads the full YAML, builds governance components from the `presidium:` block, wraps Civitas components, and delegates lifecycle to Civitas

---

## Functional Requirements

### FR-1: Single YAML File

**FR-1.1**: Users MUST be able to configure both Civitas runtime and Presidium governance in a single topology YAML file.
**FR-1.2**: The Presidium configuration MUST live under a `presidium:` top-level key.
**FR-1.3**: Civitas MUST accept the `presidium:` key without error (added to `_KNOWN_CONFIG_KEYS`).
**FR-1.4**: Civitas MUST ignore the `presidium:` block — it does not parse or validate its contents.

**Scenario**: User has a single `topology.yaml` with `transport:`, `supervision:`, `plugins:`, and `presidium:` blocks. Running `civitas run --topology topology.yaml` starts the Civitas runtime. Running via `GovernedRuntime.from_config("topology.yaml")` starts the runtime with governance.

### FR-2: GovernedRuntime Entry Point

**FR-2.1**: Presidium MUST provide `GovernedRuntime.from_config(path)` that reads the full YAML file.
**FR-2.2**: `GovernedRuntime.from_config()` MUST extract the `presidium:` block, then pass the remaining config to Civitas's `Runtime.from_config_dict()`.
**FR-2.3**: `GovernedRuntime` MUST delegate `start()`, `stop()`, `ask()`, `send()`, and all other Runtime methods to the underlying Civitas Runtime.
**FR-2.4**: `GovernedRuntime` MUST wrap Civitas components with governance layers during startup:
  - `ModelProvider` → `GovernedModelProvider`
  - `ToolProvider` → `GovernedToolProvider`
  - `AuditSink` → `AuditEnricher`
**FR-2.5**: If no `presidium:` block is present in the YAML, `GovernedRuntime` MUST behave identically to `Runtime` (governance is optional, not mandatory).

### FR-3: Civitas-Side Changes (Minimal)

**FR-3.1**: Civitas MUST add `"presidium"` to `_KNOWN_CONFIG_KEYS` in `runtime.py`.
**FR-3.2**: Civitas MUST provide `Runtime.from_config_dict(config: dict, agent_classes: dict | None = None) -> Runtime` that accepts a pre-parsed YAML dict instead of a file path. This is a refactor of the existing `from_config()` — extract the dict-loading logic, keep the file-loading version as a convenience wrapper.

### FR-4: Presidium YAML Schema

**FR-4.1**: The `presidium:` block MUST support these sub-keys:
```yaml
presidium:
  registry:
    backend: in_memory          # in_memory | sqlite | postgres (contrib)
    db_path: ./presidium.db     # sqlite only
    default_trust: 0.5          # initial trust for new agents
    trust_decay_rate: 0.01      # per hour

  policies:                     # list of PolicyRule definitions
    - name: enforce-grants
      stage: pre_tool
      expression: "!agent.grants.exists(g, request.resource in g.resources && request.action in g.actions)"
      decision: deny
      reason: "No grant for this resource/action"
      priority: 100

  credentials:
    backend: env                # env | file | vault (contrib) | aws (contrib)

  approval:
    backend: callback           # callback | slack (contrib) | temporal (contrib)
    default_timeout: 300

  audit:
    enrichment: true
    cache_ttl: 5.0

  agents:                       # per-agent governance config
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
```

**FR-4.2**: Unknown keys under `presidium:` MUST be rejected with a clear error (same pattern as Civitas's own key validation).
**FR-4.3**: The `presidium.agents` block MUST map agent names to governance config (owner, grants). These are wired to the AgentRegistry at startup.
**FR-4.4**: The `presidium.policies` block MUST be loaded and compiled by the CelPolicyEngine at startup.

### FR-5: Startup Sequence

**FR-5.1**: The `GovernedRuntime.from_config()` startup sequence MUST be:
  1. Read full YAML file
  2. Resolve `${VAR_NAME}` substitutions (Civitas's `substitute_vars()`)
  3. Extract and validate `presidium:` block
  4. Pass remaining config to `Runtime.from_config_dict()` to build Civitas runtime
  5. Build Presidium components from `presidium:` block:
     - AgentRegistry (from `presidium.registry`)
     - PolicyEngine with compiled CEL rules (from `presidium.policies`)
     - CredentialProvider (from `presidium.credentials`)
     - ApprovalService (from `presidium.approval`)
     - AuditEnricher (from `presidium.audit`)
  6. Register per-agent governance data (from `presidium.agents`): owner, grants → AgentRegistry
  7. Wrap Civitas components:
     - Replace ModelProvider with GovernedModelProvider
     - Replace ToolProvider with GovernedToolProvider
     - Replace AuditSink with AuditEnricher (wrapping original sink)
  8. Start Civitas runtime (delegates to `Runtime.start()`)

### FR-6: Programmatic API

**FR-6.1**: `GovernedRuntime` MUST also support programmatic construction (not just YAML):
```python
runtime = GovernedRuntime(
    civitas_runtime=Runtime(supervisor=...),
    registry=InMemoryRegistry(),
    policy_engine=CelPolicyEngine(rules=[...]),
    credential_provider=EnvCredentialProvider(),
    approval_service=CallbackApprovalProvider(),
)
```
**FR-6.2**: The programmatic API MUST accept all governance components as optional — missing components use defaults.

---

## Non-Functional Requirements

### NFR-1: Zero Civitas Code Impact
- Only 2 changes to Civitas: add `"presidium"` to known keys, add `from_config_dict()` method
- No new Civitas dependencies, no new imports, no behavioral changes
- Civitas without Presidium works exactly as before

### NFR-2: Backwards Compatibility
- Existing topology YAML files without `presidium:` block MUST continue to work with both `Runtime` and `GovernedRuntime`
- `GovernedRuntime` without governance config is equivalent to `Runtime`

### NFR-3: Error Messages
- Invalid `presidium:` config MUST produce clear error messages (same quality as Civitas's own config errors)
- Missing optional extras (e.g., `presidium-contrib[vault]` not installed) MUST produce helpful install hints

---

## Design Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| T1 | Config location | Single YAML file, `presidium:` top-level key | One file to manage. Civitas ignores the block. Presidium reads it. |
| T2 | Entry point | `GovernedRuntime.from_config()` wraps `Runtime.from_config_dict()` | Presidium controls startup without replacing Civitas. Clean delegation. |
| T3 | Civitas changes | 2 minimal changes: known key + from_config_dict | Smallest possible Civitas surface. No new deps, no new imports, no behavioral changes. |
| T4 | Component wrapping | Replace providers at startup, before agents start | Governance wrappers intercept all calls from the first message. No gap. |
| T5 | Per-agent config | `presidium.agents` block maps names to owner + grants | Centralizes governance config in one place. Agent code stays clean. |

---

## Out of Scope (M2)

- `civitas run` CLI integration (Presidium CLI in M5)
- Hot-reload of presidium config without restart — M3
- Separate presidium.yaml file support (single file is sufficient for M2)
- Presidium topology validation CLI command — M5
