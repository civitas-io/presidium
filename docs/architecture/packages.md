# Package Map

> What each package does, its boundaries, and dependencies.

![Interface-First Architecture](../assets/interface-first-architecture.svg)

## Overview

Presidium ships as two packages. `presidium` is the interface library: pure Protocol definitions, no heavy dependencies, installable anywhere. `presidium-contrib` is the adapters and reference implementations: OPA, Vault, LiteLLM, Slack, and the novel components that have no existing product equivalent.

This follows the same pattern as Civitas (`civitas` + `civitas-contrib`): the core package defines the contracts, contrib provides the implementations.

```
presidium/                          # Interface library (pip install presidium)
  registry.py                       # AgentRecord, GrantSet, TrustScore protocols
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
    litellm_proxy.py                 # LiteLLM GovernedModelProvider adapter
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
| LLM Gateway | `GovernedModelProvider` | In-process grant checks + rate limits | | LiteLLM Proxy, Portkey | |
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

class PolicyEngine(Protocol):
    async def evaluate(
        self,
        agent: str,
        action: str,
        context: dict[str, Any],
    ) -> PolicyDecision: ...

class CelPolicyEngine:
    """Default: evaluates CEL expressions in-process. No sidecar required."""

    def __init__(self, rules_path: Path) -> None: ...

    async def evaluate(
        self,
        agent: str,
        action: str,
        context: dict[str, Any],
    ) -> PolicyDecision: ...
```

CEL (Common Expression Language) is the default because it's embeddable, has a Python implementation (`cel-python`), and is the direction Kubernetes is moving for admission policies. No sidecar, no network call, no Rego to learn.

### Agent Registry

```python
@dataclass
class GrantSet:
    capabilities: list[str]
    llm_providers: list[str]
    tools: list[str]
    budget_usd_per_hour: float | None

@dataclass
class AgentRecord:
    name: str
    version: str
    owner: str
    grants: GrantSet
    trust_score: float
    state: AgentState

class AgentRegistry(Protocol):
    async def register(self, record: AgentRecord) -> None: ...
    async def lookup(self, name: str) -> AgentRecord | None: ...
    async def update_trust(self, name: str, delta: float) -> None: ...
    async def get_grants(self, name: str) -> GrantSet | None: ...
```

No existing product tracks agent grants and trust scores together. This is novel territory.

### Credential Provider

```python
class CredentialProvider(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def rotate(self, key: str) -> str: ...

class EnvCredentialProvider:
    """Default: reads from environment variables."""
    async def get(self, key: str) -> str | None: ...

class FileCredentialProvider:
    """Default: reads from a local secrets file (dev only)."""
    def __init__(self, path: Path) -> None: ...
    async def get(self, key: str) -> str | None: ...
```

### Trust Scorer

```python
@dataclass
class TrustSignal:
    source: str          # "policy_violation", "eval_score", "human_approval"
    value: float         # normalized 0.0–1.0
    weight: float
    timestamp: datetime

class TrustScorer(Protocol):
    async def score(self, agent: str, signals: list[TrustSignal]) -> float: ...
    async def current(self, agent: str) -> float: ...

class RuleBasedTrustScorer:
    """Default: weighted average of signals with configurable decay."""
    async def score(self, agent: str, signals: list[TrustSignal]) -> float: ...
```

No existing product does trust scoring for AI agents. The reference implementation in `presidium-contrib` adds learning from historical patterns.

### HITL / Approval Service

```python
@dataclass
class ApprovalRequest:
    agent: str
    action: str
    context: dict[str, Any]
    timeout_seconds: int = 300

@dataclass
class ApprovalResponse:
    approved: bool
    reviewer: str | None
    reason: str | None

class ApprovalService(Protocol):
    async def request(self, req: ApprovalRequest) -> ApprovalResponse: ...

class CallbackApprovalProvider:
    """Default: calls a Python callback. Useful for tests and CLI tools."""
    def __init__(self, callback: Callable[[ApprovalRequest], Awaitable[ApprovalResponse]]) -> None: ...
```

### Audit Enricher

```python
@dataclass
class AuditEvent:
    agent: str
    action: str
    decision: PolicyDecision
    trust_score: float
    context: dict[str, Any]
    timestamp: datetime

class AuditEnricher(Protocol):
    async def emit(self, event: AuditEvent) -> None: ...

class InProcessAuditEnricher:
    """Default: enriches events and forwards to Civitas AuditSink."""
    def __init__(self, sink: AuditSink) -> None: ...
    async def emit(self, event: AuditEvent) -> None: ...
```

Presidium doesn't own the audit destination. It enriches events with governance context (policy decision, trust score, grant set) and forwards to Civitas's `AuditSink`, which already has adapters for Datadog, Splunk, and ELK.

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

**`adapters/litellm_proxy.py`** — LiteLLM Proxy `GovernedModelProvider`. Routes LLM calls through a running LiteLLM proxy. Inherits LiteLLM's provider support (100+ models).

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
