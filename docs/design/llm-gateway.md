# Design: LLM Gateway

> Governed LLM access — authorization via Presidium, operations via a pluggable gateway backend.

**Status:** Draft (revised 2026-07-07 — generalized from a single AgentGateway integration to a
pluggable `LLMGatewayBackend` Protocol with multiple adapters; see changelog below)
**Package:** `presidium` (`GovernedModelProvider` + new `LLMGatewayBackend` Protocol) +
`presidium-contrib[agentgateway|litellm|kong|...]` (backend adapters)
**Milestone:** M2 (authorization) / M3 (AgentGateway adapter, post-execution validation) / M3+
(backend pluggability, this revision)

> **2026-07-07 changelog:** the operations half of this design was implicitly hardcoded to
> AgentGateway (`GovernedModelProvider` called `AgentGatewayClient` directly). This revision
> extracts that dependency into a new `LLMGatewayBackend` Protocol so any OpenAI-wire-compatible
> gateway can be plugged in. **AgentGateway remains the reference/fully-built adapter.** LiteLLM
> Proxy is the current leading candidate for a second fully-built adapter (evidence below), but
> **this choice is explicitly not frozen** and may change based on market/customer signal — Kong,
> Portkey, Cloudflare AI Gateway, Helicone, and TrueFoundry are stubbed (interface-conformant,
> `NotImplementedError` bodies) so switching the second pick later is a small, contained change,
> not a redesign.

## Problem Statement

Agents call LLMs without constraints. There's no per-agent rate limiting, no cost tracking, no budget enforcement, no routing logic. A single runaway agent can burn through an entire organization's API budget in hours. Teams have no visibility into which agent is calling which model at what cost.

## Goals

1. Grant-based authorization: can this agent use this model? (Presidium)
2. Trust-gated decisions: does the agent's trust level allow this action? (Presidium)
3. Approval routing for sensitive actions (Presidium)
4. Rate limiting, cost tracking, provider routing (AgentGateway)
5. Post-execution output validation via `POST_LLM` stage (M3)

## Non-Goals

- LLM output quality evaluation (hallucination, toxicity) — separate concern (NeMo Guardrails, Guardrails AI)
- Model fine-tuning or training — out of scope
- Caching/semantic caching — potential future feature
- Reimplementing rate limiting or cost tracking that a backend already provides
- **Freezing the second backend adapter choice.** LiteLLM is the current evidence-based lean, not
  a commitment — the whole point of `LLMGatewayBackend` being a Protocol is that this can change
  without touching `GovernedModelProvider` or any agent code.

## Responsibility Split

Presidium and AgentGateway serve different layers of the governance stack:

| Concern | Owner | Why |
|---|---|---|
| **Authorization** (can agent X use model Y?) | Presidium | Grant-based, trust-gated, CEL policies |
| **Approval routing** (REQUIRE_APPROVAL decisions) | Presidium | HITL workflow, fail-closed timeout |
| **Audit enrichment** (governance context on events) | Presidium | Agent identity, trust tier, owner |
| **Rate limiting** (requests/min, tokens/min) | AgentGateway | Native, per-agent, configurable |
| **Cost tracking** (USD per call, budget enforcement) | AgentGateway | Native, per-provider pricing tables |
| **Provider routing** (agent A → Claude, agent B → GPT-4) | AgentGateway | Native, rule-based routing |
| **Content filtering** (guardrails, moderation) | AgentGateway | Multi-layered, webhook-extensible |
| **Post-execution validation** (schema, PII, content policy) | Presidium (`POST_LLM`) | CEL-based output policies (M3) |

**Architecture:** Presidium's `GovernedModelProvider.check()` runs *before* the call reaches the
configured gateway backend. If the check returns DENY, the call never leaves the process. If
ALLOW, the call proceeds to the backend (AgentGateway, LiteLLM, or another `LLMGatewayBackend`
implementation) which handles routing, rate limiting, and cost tracking.

```
Agent calls LLM
    ↓
GovernedModelProvider.check()     ← Presidium (authorization)
    ↓ ALLOW
LLMGatewayBackend                 ← Operations (routing, rate limits, cost) — pluggable
    ↓ response
GovernedModelProvider.post_check() ← Presidium POST_LLM (M3, output validation)
    ↓
Agent receives response
```

## Design

### The `LLMGatewayBackend` Protocol (pluggable operations layer)

`GovernedModelProvider` does not call any specific gateway product directly. It depends on a
`Protocol` that any OpenAI-wire-compatible gateway can satisfy — matching the same
interface-library discipline as `PolicyEngine`/`CredentialProvider`/`TrustScorer` in `presidium`
core:

```python
class LLMGatewayBackend(Protocol):
    """Operations backend for GovernedModelProvider: routing, rate limits, cost tracking.

    Presidium owns authorization (grants, trust, CEL policy) and always runs it BEFORE this is
    called. The backend owns operations — it never sees a request Presidium already denied.
    """

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        agent_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]: ...

    async def list_models(self) -> list[dict[str, Any]]: ...

    async def health(self) -> bool: ...
```

This is a minimal, OpenAI-wire-shaped contract — the existing `AgentGatewayClient`
(`presidium_contrib.agentgateway.client`) already structurally satisfies it unchanged; it becomes
the reference implementation of `LLMGatewayBackend` rather than a hardcoded dependency.

#### Backend adapters (`presidium-contrib`)

| Adapter | Package | Status | Why |
|---|---|---|---|
| **AgentGateway** | `presidium_contrib.agentgateway` | ⚠️ **LLM side fully built, MCP/A2A side not** (see below) | Linux Foundation, Rust, one data plane for LLM + MCP + A2A, native CEL policies + OTel. Already the adapter this design was originally hardcoded to. **2026-08-24**: latest is `v1.4.1`; a real, HIGH-severity security advisory (GHSA-mvgg-jvj2-4frq, session/authz confusion across routes) is fixed in `v1.4.0` — pin `>=1.4.0` in any real deployment or test fixture. Full vendor research: [`agentgateway-vendor-research-2026-08.md`](agentgateway-vendor-research-2026-08.md). |
| **LiteLLM Proxy** | `presidium_contrib.litellm` | 🟡 **Leading candidate for 2nd fully-built adapter — not frozen** | Highest OSS adoption signal found (52.8k GitHub stars vs. Kong's 43.7k), MIT license (zero friction with Presidium's Apache 2.0, unlike Helicone's GPLv3), Python-native SDK (not just an HTTP target), fully self-hostable (Docker/K8s/Terraform, no hyperscaler dependency), named production users (Netflix, Adobe, Samsara). **Caveats weighed, not ignored:** a real CVE history on its auth path (CVE-2026-42208 SQLi, plus CVE-2026-47101/47102/40217) for a component that is itself a trust boundary; full-featured deployment wants a Postgres+Redis backend (more operational surface than AgentGateway's single Rust binary); its ~471M/30-day PyPI download figure is likely inflated by transitive-dependency installs and should not be read as 471M people running it as a governed proxy. **This is a lean, not a lock-in** — see the note at the top of this doc. |
| Kong AI Gateway | `presidium_contrib.kong` | ⚪ Stubbed | Strong enterprise backing ($345M Series E, Fortune 500 customers) but not Python-native (generic HTTP gateway) and requires a Konnect control plane for full features. |
| Portkey AI Gateway | `presidium_contrib.portkey` | ⚪ Stubbed | Acquired by Palo Alto Networks (May 2026); SaaS-only post-acquisition, no self-hosted path — conflicts with Presidium's no-hyperscaler-lock-in stance. |
| Cloudflare AI Gateway | `presidium_contrib.cloudflare_ai_gateway` | ⚪ Stubbed | SaaS-only, all traffic routes through Cloudflare — directly conflicts with self-hostability. |
| Helicone AI Gateway | `presidium_contrib.helicone` | ⚪ Stubbed | GPLv3 (copyleft friction with Apache 2.0), acquired by Mintlify (Mar 2026, standalone future uncertain), modest adoption (608 stars). |
| TrueFoundry AI Gateway | `presidium_contrib.truefoundry` | ⚪ Stubbed | Too early-stage (13 GitHub stars, no named customers, no dedicated gateway repo) for a production reference adapter today. |

"Stubbed" means the adapter module exists, implements `LLMGatewayBackend`'s method signatures, and
raises `NotImplementedError` with a clear message — enough for `mypy --strict` conformance and to
reserve the extras name (`presidium-contrib[kong]`, etc.) without committing implementation effort
until one is actually chosen to build out.

### Gateway as ModelProvider

```python
class GovernedModelProvider(ModelProvider):
    """LLM gateway that enforces rate limits, cost tracking, and routing.

    Delegates operations to a pluggable LLMGatewayBackend (AgentGateway by default; see the
    backend adapter table above for alternatives).
    """

    def __init__(self, backend: LLMGatewayBackend, registry: AgentRegistry, ...) -> None:
        self._backend = backend
        ...

    async def chat(
        self,
        messages: list[Message],
        *,
        agent_name: str,
        **kwargs: Any,
    ) -> ModelResponse:
        record = await self.registry.lookup(agent_name)

        # 1. Authorization (Presidium — grants, trust, CEL policy)
        await self.check(agent_name, record, messages)

        # 2. Operations (backend — routing, rate limits, cost tracking)
        response = await self._backend.chat(messages, agent_name=agent_name, **kwargs)

        return response
```

### Rate Limiting

Uses Civitas's bounded mailbox mechanism — native backpressure, not a separate rate limiter:

```yaml
llm_gateway:
  rate_limits:
    default:
      requests_per_minute: 60
      tokens_per_minute: 100000
    overrides:
      analyst-*:
        requests_per_minute: 30
      writer-*:
        requests_per_minute: 120
```

### Cost Tracking

```python
@dataclass
class CostRecord:
    agent_name: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime

@dataclass
class BudgetConfig:
    agent_name: str
    daily_limit_usd: float
    monthly_limit_usd: float
    action_on_exceed: Literal["deny", "warn", "throttle"]
```

### Provider Routing

```yaml
llm_gateway:
  routing:
    default_provider: anthropic
    overrides:
      analyst-*:
        provider: anthropic
        model: claude-sonnet-4-20250514
      writer-*:
        provider: openai
        model: gpt-4o
      budget-agent-*:
        provider: anthropic
        model: claude-haiku
```

### Context Budget

Token consumption is a governance primitive, not just a cost concern. Runaway context growth is a
failure mode: an agent accumulating unbounded context degrades output quality before it exceeds
any dollar threshold.

Model context windows as OS CPU scheduling — each agent gets a declared budget; the supervisor
enforces it at the transport layer:

```python
@dataclass
class ContextBudget:
    agent_name: str
    max_tokens_per_request: int       # hard cap on individual call
    max_tokens_per_session: int       # cumulative cap across a task session
    warn_threshold: float = 0.8       # emit SIGWARN at 80% consumed
    action_on_exceed: Literal["deny", "truncate", "summarize"]

class ContextWindow:
    """Per-agent token accounting maintained by GovernedModelProvider."""
    consumed: int = 0
    budget: ContextBudget = ...

    def check(self, estimated_tokens: int) -> None:
        if self.consumed + estimated_tokens > self.budget.max_tokens_per_session:
            raise ContextBudgetExceeded(agent=self.budget.agent_name, consumed=self.consumed)
        if (self.consumed + estimated_tokens) / self.budget.max_tokens_per_session >= self.budget.warn_threshold:
            self._emit_sigwarn()
```

`GovernedModelProvider.chat()` checks and records against `ContextWindow` before and after each
call. Budget state persists to Civitas `StateStore` so it survives supervisor restarts.

BudgetConfig (cost) and ContextBudget (tokens) are separate configurations — cost limits prevent
runaway spend; context limits prevent quality degradation. Both are enforced at the same gateway
layer.

## Open Questions

- Should the gateway support failover (if Anthropic is down, fall back to OpenAI)? (Note: a
  backend like AgentGateway or LiteLLM may already do this internally — check before building a
  second failover layer in Presidium.)
- How does cost tracking persist across restarts? Use Civitas's StateStore?
- Should budget enforcement be per-agent, per-team, or per-organization?
- Integration with Civitas's existing ModelProvider plugins (AnthropicProvider, etc.) — is this a
  `presidium_contrib.direct` backend (no gateway product, straight to civitas's own provider
  plugins) for the smallest-footprint deployment tier, below even AgentGateway?
- **When does the second backend get promoted from "leading candidate" to "built"?** Proposed
  trigger: either a specific customer/design-partner requirement names one, or `agentgateway`'s
  adapter is stable enough that the team has bandwidth for a second — not a fixed date.
