# Package Map

> What each package does, its boundaries, and dependencies.
> Last updated: 2026-05-05

![Interface-First Architecture](../assets/interface-first-architecture.svg)

## Overview

Presidium ships as two packages. `presidium` is the interface library: pure Protocol definitions, no heavy dependencies, installable anywhere. `presidium-contrib` is the adapters and reference implementations: OPA, Vault, AgentGateway, Slack, and the novel components that have no existing product equivalent.

This follows the same pattern as Civitas (`civitas` + `civitas-contrib`): the core package defines the contracts, contrib provides the implementations.

```
presidium/                          # Interface library (pip install presidium)
  registry.py                       # AgentRecord, Grant, TrustScorer protocols
  policy.py                         # PolicyEngine protocol + CelPolicyEngine default
  credentials.py                    # CredentialProvider protocol
  llm_gateway.py                    # GovernedModelProvider protocol
  mcp_gateway.py                    # GovernedToolProvider protocol
  audit.py                          # AuditEnricher protocol (wraps Civitas AuditSink)
  hitl.py                           # ApprovalService protocol
  trust.py                          # TrustScorer protocol

presidium-contrib/                   # Adapters + reference impls
  adapters/
    opa.py                           # OPA PolicyEngine adapter
    cedar.py                         # Cedar PolicyEngine adapter
    vault.py                         # HashiCorp Vault CredentialProvider
    agentgateway.py              # AgentGateway adapter (LLM + MCP routing)
    slack_approval.py                # Slack-based HITL adapter
    temporal_approval.py             # Temporal human task adapter
  reference/
    postgres_registry.py             # Reference impl: agent registry (novel)
    mcp_governance.py                # Reference impl: MCP governance (novel)
    trust_scorer.py                  # Reference impl: trust scoring (novel)
```

![Dependency Graph](../assets/dependency-graph.svg)

---

## Component Map

![Build vs. Wrap](../assets/product-mapping.svg)

| Component | Interface (presidium) | Library Mode Default | Service Mode | Existing Products (Adapters) | Novel (Reference Impl) |
|---|---|---|---|---|---|
| Policy Engine | `PolicyEngine` | `CelPolicyEngine` (in-process CEL) | `PolicyService` GenServer | OPA, Cedar | |
| Agent Registry | `AgentRegistry` | `InMemoryRegistry` / `SqliteRegistry` | `RegistryService` (Postgres) | | Postgres registry with grants + trust |
| Credential Provider | `CredentialProvider` | `EnvCredentialProvider` / `FileCredentialProvider` | | HashiCorp Vault, AWS Secrets Manager | |
| Trust Scorer | `TrustScorer` | `RuleBasedTrustScorer` | `LearningTrustScorer` | | Trust scoring for AI agents |
| HITL / Approval | `ApprovalService` | `CallbackApprovalProvider` | | Slack, Temporal, PagerDuty | |
| Audit Enricher | `AuditEnricher` | `InProcessAuditEnricher` | | Datadog, Splunk, ELK (via Civitas AuditSink) | |
| LLM Gateway | `GovernedModelProvider` | In-process grant checks + rate limits | | AgentGateway (Linux Foundation) | |
| MCP Governance | `GovernedToolProvider` | In-process ACL checks | | | MCP governance (no existing product) |

---

## presidium (core)

**Protocol definitions and lightweight defaults.**

The core package has no heavy dependencies. Every component is a Protocol — structural typing, not inheritance. Defaults are in-process implementations suitable for development and small deployments.

### Policy Engine

```python
class PolicyDecision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"

class EvaluationStage(Enum):
    PRE_TOOL = "pre_tool"
    PRE_LLM = "pre_llm"
    PRE_MESSAGE = "pre_message"
    REGISTRATION = "registration"

@dataclass
class PolicyResult:
    decision: PolicyDecision
    policy_name: str
    reason: str | None = None
    approvers: list[str] | None = None
    enforcement: EnforcementMode = EnforcementMode.HARD

@dataclass
class EvaluationContext:
    agent: AgentRecord       # identity, grants, trust, status, owner
    request: ActionRequest   # resource + action + parameters
    time: datetime

class PolicyEngine(Protocol):
    def load_policies(self, rules: list[PolicyRule]) -> None: ...
    async def evaluate(
        self, stage: EvaluationStage, context: EvaluationContext
    ) -> PolicyResult: ...

class CelPolicyEngine:
    """Default: compiles CEL expressions at load time, evaluates in-process (1-3ms).
    Fail-closed: evaluation errors return DENY. No sidecar required."""

    def load_policies(self, rules: list[PolicyRule]) -> None: ...
    async def evaluate(
        self, stage: EvaluationStage, context: EvaluationContext
    ) -> PolicyResult: ...
```

> See [policy-engine design doc](../design/policy-engine.md) for full data model, enforcement modes, CEL expression format, and design decisions.

CEL (Common Expression Language) is the default because it's embeddable, has a Python implementation (`cel-python`), and is the direction Kubernetes is moving for admission policies. No sidecar, no network call, no Rego to learn.

### Agent Registry

```python
@dataclass
class Grant:
    resources: list[str]              # ["tool:database", "llm:claude-sonnet"]
    actions: list[str]                # ["read", "write", "invoke"]
    scope: dict[str, str] = field(default_factory=dict)
    condition: str | None = None      # CEL expression evaluated at policy time
    expires_at: datetime | None = None

@dataclass
class AgentRecord:
    # Identity
    agent_id: str                     # SPIFFE-compatible URI: presidium://{trust_domain}/{path}
    name: str
    public_key: str                   # Ed25519 public key (base64)
    # Governance
    grants: list[Grant] = field(default_factory=list)
    trust_value: float = 0.5
    trust_tier: TrustTier = TrustTier.STANDARD
    status: AgentStatus = AgentStatus.REGISTERED
    # Accountability
    owner: str | None = None
    parent_agent_id: str | None = None
    revision: int = 0

class AgentRegistry(Protocol):
    async def register(self, record: AgentRecord) -> AgentRecord: ...
    async def lookup(self, name: str) -> AgentRecord | None: ...
    async def lookup_by_id(self, agent_id: str) -> AgentRecord | None: ...
    async def add_grant(self, name: str, grant: Grant) -> AgentRecord: ...
    async def has_grant(self, name: str, resource: str, action: str) -> bool: ...
    async def record_trust_event(self, name: str, event: TrustEvent) -> AgentRecord: ...
    async def update_status(self, name: str, status: AgentStatus) -> AgentRecord: ...
```

> See [agent-registry design doc](../design/agent-registry.md) for full data model, SPIFFE identity format, dynamic spawning rules, and design decisions.

No existing product tracks agent grants and trust scores together. This is novel territory.

### Credential Provider

```python
class CredentialProvider(Protocol):
    async def get(
        self,
        agent_id: str,
        credential_name: str,
        grants: list[Grant],
    ) -> str | None: ...
    async def close(self) -> None: ...

class EnvCredentialProvider:
    """Default: reads from os.environ. Checks grants before resolving.
    Credential resource format: credential:{name}"""
    async def get(self, agent_id: str, credential_name: str, grants: list[Grant]) -> str | None: ...

class FileCredentialProvider:
    """Default: reads from a key=value file (dev only). Same grant checking."""
    def __init__(self, path: Path) -> None: ...
    async def get(self, agent_id: str, credential_name: str, grants: list[Grant]) -> str | None: ...
```

> See [credential-provider design doc](../design/credential-provider.md) for grant integration, topology YAML wiring, audit event format, and design decisions.

### Trust Scorer

```python
class TrustEvent(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    POLICY_VIOLATION = "policy_violation"
    HUMAN_OVERRIDE = "human_override"

class TrustScorer(Protocol):
    @property
    def value(self) -> float: ...       # 0.0 - 1.0
    @property
    def tier(self) -> TrustTier: ...
    @property
    def last_updated(self) -> datetime: ...
    def record_event(self, event: TrustEvent) -> None: ...

class LinearTrustScore:
    """Default: linear decay, 3 tiers (TRUSTED >= 0.7, STANDARD 0.3-0.7, RESTRICTED < 0.3).
    SUCCESS +0.02, FAILURE -0.05, POLICY_VIOLATION -0.10, decay -0.01/hr."""
```

> See [agent-registry design doc](../design/agent-registry.md) for trust tier thresholds, decay model, and the AGT-style learning scorer in presidium-contrib.

No existing product does trust scoring for AI agents. The reference implementation in `presidium-contrib` adds learning from historical patterns.

### HITL / Approval Service

```python
@dataclass
class ApprovalRequest:
    request_id: str                       # UUID
    agent_id: str                         # presidium:// URI
    resource: str                         # e.g. "tool:database"
    action: str                           # e.g. "write"
    reason: str                           # from PolicyResult.reason
    approvers: list[str]                  # from PolicyRule.approvers
    context: dict[str, Any]
    policy_name: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    timeout_seconds: float = 1800.0

@dataclass
class ApprovalDecision:
    request_id: str
    approved: bool
    decided_by: str
    reason: str | None = None

class ApprovalService(Protocol):
    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision: ...
    async def list_pending(self) -> list[ApprovalRequest]: ...
    async def decide(self, request_id: str, decision: ApprovalDecision) -> None: ...

class CallbackApprovalProvider:
    """Default: programmatic callback or auto-approve/deny flags. No infrastructure required."""
    auto_approve: bool
    auto_deny: bool
    callback: Callable | None
    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision: ...
```

> See [approval-service design doc](../design/approval-service.md) for PEP integration, Slack/Temporal contrib adapters, and the connection to M4 autonomy progression.

### Audit Enricher

```python
# AuditEvent is Civitas's TypedDict — Presidium does not define its own
from civitas.audit.types import AuditEvent, AuditSink

class AuditEnricher(Protocol):
    """Structural subtype of AuditSink. Drop-in replacement that adds governance context."""
    async def emit(self, event: AuditEvent) -> None: ...
    async def flush(self) -> None: ...
    async def close(self) -> None: ...

class InProcessAuditEnricher:
    """Default: looks up agent in registry, adds details['governance'] dict, forwards to sink.
    Fail-open: enrichment errors forward the original event rather than dropping it."""
    def __init__(self, downstream: AuditSink, registry: AgentRegistry, cache_ttl: float = 5.0) -> None: ...
    async def emit(self, event: AuditEvent) -> None: ...
```

Enrichment adds a `governance` key to `event["details"]`:

```python
# Before enrichment (Civitas event)
{"sender": "researcher", "recipient": "database_tool", "type": "tool_call"}

# After enrichment (Presidium adds governance key)
{"sender": "researcher", "recipient": "database_tool", "type": "tool_call",
 "governance": {"agent_id": "presidium://acme.com/prod/researcher",
                "trust_value": 0.72, "trust_tier": "trusted", "owner": "alice@acme.com"}}
```

> See [audit-enricher design doc](../design/audit-enricher.md) for the full event type catalog, topology YAML wiring, and design decisions.

Presidium doesn't own the audit destination. It enriches events with governance context and forwards to Civitas's `AuditSink`, which already has adapters for Datadog, Splunk, and ELK.

### LLM Gateway

```python
class GovernedModelProvider(Protocol):
    """Wraps civitas.ModelProvider with grant checks and rate limiting."""
    async def complete(
        self,
        agent: str,
        messages: list[Message],
        model: str | None = None,
    ) -> Completion: ...

    async def check_grants(self, agent: str, model: str) -> bool: ...
    async def remaining_budget(self, agent: str) -> float | None: ...
```

### MCP Governance

```python
class GovernedToolProvider(Protocol):
    """Wraps civitas.ToolProvider with ACL checks and audit logging."""
    async def call(
        self,
        agent: str,
        tool: str,
        params: dict[str, Any],
    ) -> ToolResult: ...

    async def check_access(self, agent: str, tool: str) -> bool: ...
```

No existing product governs MCP tool access at this level. The reference implementation in `presidium-contrib` adds tool poisoning detection and credential redaction.

---

## presidium-contrib

**Adapters for existing products and reference implementations for novel components.**

### Adapters (existing products)

These wrap products that already exist. The adapter implements the Presidium protocol; the underlying product does the work.

**`adapters/opa.py`** — OPA `PolicyEngine` adapter. Calls the OPA REST API. Use when you already run OPA and want to reuse your Rego policies.

**`adapters/cedar.py`** — Cedar `PolicyEngine` adapter. Use when you need Cedar's authorization model (entity-based, fine-grained).

**`adapters/vault.py`** — HashiCorp Vault `CredentialProvider`. Reads secrets from Vault's KV engine. Handles token renewal.

**`adapters/agentgateway.py`** — AgentGateway `GovernedModelProvider` + `GovernedToolProvider`. Routes LLM and MCP calls through AgentGateway (Linux Foundation). Native CEL policy engine, OpenTelemetry observability, A2A protocol support. Replaces LiteLLM adapter — AgentGateway is agent-centric (LLM + MCP + A2A) rather than LLM-centric.

**`adapters/slack_approval.py`** — Slack `ApprovalService`. Posts approval requests to a Slack channel with approve/deny buttons. Waits for response via Slack Events API.

**`adapters/temporal_approval.py`** — Temporal `ApprovalService`. Creates a Temporal human task workflow. Integrates with existing Temporal deployments.

### Reference Implementations (novel)

These implement components where no existing product fits. They're production-ready but not wrappers.

**`reference/postgres_registry.py`** — `AgentRegistry` backed by Postgres. Stores agent records, grant sets, and trust score history. Supports the `RegistryService` GenServer for service mode.

**`reference/mcp_governance.py`** — `GovernedToolProvider` with full MCP governance: ACL enforcement, tool poisoning detection (hash-based), credential redaction from parameters, and per-call audit logging.

**`reference/trust_scorer.py`** — `LearningTrustScorer`. Starts with rule-based scoring, then learns from the decision journal (action, context, outcome, human decision) to improve signal weighting over time.

---

## Dependency Graph

![Dependency Graph](../assets/dependency-graph.svg)
