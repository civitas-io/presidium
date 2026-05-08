# Package Map

> What each package does, its boundaries, and dependencies.

## Overview

Presidium is a monorepo with independently installable packages. Each package owns a specific governance concern and integrates with Civitas at well-defined extension points.

```mermaid
graph TD
    SDK["presidium-sdk<br/><i>unified API</i>"]
    SDK --> Eval["presidium-eval"]
    SDK --> LLMGw["presidium-llm-gateway"]
    SDK --> MCPGw["presidium-mcp-gateway"]
    SDK --> Policy["presidium-policy"]
    SDK --> Registry["presidium-registry<br/><i>shared dependency</i>"]
    Eval --> Registry
    LLMGw --> Registry
    MCPGw --> Registry
    Policy --> Registry
```

---

## presidium-registry

**Agent identity, capability registration, and trust tracking.**

### Responsibility

- Define agent identities (name, version, owner, capabilities)
- Track agent lifecycle states (registered, starting, running, stopped, suspended)
- Maintain trust scores based on runtime behavior
- Provide lookup APIs for other packages (policy, gateways, eval)

### Civitas Integration Point

- Extends `civitas.Registry` — adds governance metadata to agent registrations
- Hooks into `AgentProcess.on_start()` / `on_stop()` for lifecycle tracking

### Key Types (Planned)

```python
@dataclass
class AgentRecord:
    name: str
    version: str
    owner: str
    capabilities: list[str]
    trust_score: float
    policies: list[str]
    state: AgentState

class AgentRegistry(Protocol):
    async def register(self, record: AgentRecord) -> None: ...
    async def lookup(self, name: str) -> AgentRecord | None: ...
    async def update_trust(self, name: str, delta: float) -> None: ...
```

### Depends On

- `civitas` (registry, process)

---

## presidium-policy

**Policy definition, evaluation, and enforcement.**

### Responsibility

- Define policies in YAML (primary), with OPA Rego and Cedar support planned
- Evaluate agent actions against applicable policies
- Enforce decisions: ALLOW, DENY, REQUIRE_APPROVAL
- Integrate with Civitas supervisors (policies as supervisor config)

### Civitas Integration Point

- Hooks into `Supervisor` — policies determine restart strategies, resource limits
- Hooks into `MessageBus` — action-level enforcement before message delivery

### Key Types (Planned)

```python
class PolicyDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"

class PolicyEngine(Protocol):
    async def evaluate(
        self,
        agent: str,
        action: str,
        context: dict[str, Any],
    ) -> PolicyDecision: ...

# YAML policy example:
# policies:
#   - name: read-only-analyst
#     agents: ["analyst-*"]
#     rules:
#       - action: "write_*"
#         decision: deny
#       - action: "delete_*"
#         decision: deny
#       - action: "read_*"
#         decision: allow
```

### Depends On

- `civitas` (supervisor, bus)
- `presidium-registry` (agent lookup)

---

## presidium-llm-gateway

**LLM request routing, rate limiting, and cost tracking.**

### Responsibility

- Route LLM requests to configured providers based on agent identity/policy
- Enforce per-agent rate limits (requests/minute, tokens/minute)
- Track cost per agent, per session, per provider
- Apply content filtering hooks (pre/post LLM call)
- Budget enforcement (hard limits, soft warnings)

### Civitas Integration Point

- Implements `civitas.plugins.ModelProvider` protocol
- Uses bounded mailboxes for rate limiting (native backpressure)

### Depends On

- `civitas` (plugins)
- `presidium-registry` (agent lookup for rate limits)
- `presidium-policy` (action-level checks)

---

## presidium-mcp-gateway

**Tool access governance via MCP (Model Context Protocol).**

### Responsibility

- Control which agents can access which tools
- Detect tool poisoning (tools changing behavior post-approval)
- Redact credentials from tool call parameters
- Audit log all tool interactions
- Enforce tool-level policies (some tools require approval)

### Civitas Integration Point

- Wraps `civitas.mcp` integration
- Implements `civitas.plugins.ToolProvider` protocol

### Depends On

- `civitas` (mcp, plugins)
- `presidium-registry` (agent capabilities determine tool access)
- `presidium-policy` (tool-level policies)

---

## presidium-eval

**Governance-aware evaluation, trust feedback, and external platform integration.**

### Responsibility

- Define governance-specific evaluation metrics (`GovernanceMetrics`):
  - Policy compliance rate, denial count, approval queue depth
  - Trust score trends, grant utilization, budget consumption
  - Drift score (deviation from declared intent)
  - Mean action latency, restart count
- Provide `GovernanceEvalAgent` — extends Civitas `EvalAgent` with governance context
- Close the feedback loop: composite quality + governance scores → trust score adjustments → autonomy changes
- Define `MetricRegistry` — canonical metric + threshold config shared between in-flight and offline evaluation
- Export governance metrics to external platforms via `GovernanceExporter` protocol
- Export backends: Fiddler, Arize, Langfuse, Prometheus, Console

### Civitas Integration Point

- Extends `civitas.EvalAgent` with `GovernanceEvalAgent` (integration point 6)
- Consumes `EvalExporter` results (e.g., DeepEval scores) for composite scoring
- Writes trust score updates to `presidium-registry`
- Reads policy decisions from `presidium-policy` for compliance metrics

### Relationship to civitas[test] and civitas-contrib[deepeval]

`presidium-eval` owns governance metrics and trust feedback. It does NOT own:

- **Test harness** (`EvalTestRunner`, `EvalDataset`) → `civitas[test]` extra (civitas core)
- **DeepEval bridge** (`DeepEvalExporter`, custom `BaseMetric`) → `civitas-contrib[deepeval]`
- **Quality metrics** (`TaskCompletionMetric`, `ToolCorrectnessMetric`) → DeepEval (external)

The `GovernanceEvalAgent` consumes quality scores from exporters and governance scores from its own metrics, then produces a composite that drives trust feedback.

See [Eval Framework design doc](../design/eval-framework.md) and [DeepEval Integration design doc](../design/deepeval-integration.md) for full details.

### Key Types (Planned)

```python
@dataclass
class GovernanceMetrics:
    policy_compliance_rate: float
    denial_count: int
    trust_score_delta: float
    tool_usage_authorized: float
    llm_budget_utilization: float
    drift_score: float
    # ... see design doc for full list

class GovernanceEvalAgent(EvalAgent):
    async def on_eval_event(self, event: EvalEvent) -> CorrectionSignal | None: ...

class GovernanceExporter(Protocol):
    async def export(self, agent_name: str, metrics: GovernanceMetrics, window: TimeWindow) -> None: ...

class MetricRegistry:
    def get_metrics(self, agent_name: str, context: str = "in_flight") -> list[MetricConfig]: ...
```

### Depends On

- `civitas` (EvalAgent, EvalExporter, EvalEvent, CorrectionSignal)
- `presidium-registry` (trust score updates via `AgentRegistry.update_trust()`)
- `presidium-policy` (policy decisions for compliance metrics)

---

## presidium-sdk

**Unified developer API — the `pip install presidium` experience.**

### Responsibility

- Re-export all public APIs from sub-packages
- Provide convenience constructors and helpers
- CLI commands (`presidium run`, `presidium policy validate`, etc.)
- YAML topology extension (add governance config to Civitas topology files)
- Getting started experience

### Example API (Aspirational)

```python
from presidium import GovernedRuntime, Policy, AgentRecord

runtime = GovernedRuntime.from_topology("topology.yml")

# Or programmatic:
runtime = GovernedRuntime(
    policies=[
        Policy.read_only(agents=["analyst-*"]),
        Policy.rate_limit(agents=["*"], requests_per_minute=100),
    ],
    agents=[
        AgentRecord(name="analyst", capabilities=["read:data"]),
        AgentRecord(name="writer", capabilities=["read:data", "write:reports"]),
    ],
)

await runtime.start()
```

### Depends On

- All presidium packages
- `civitas`
