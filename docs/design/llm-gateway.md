# Design: LLM Gateway

> Governed LLM access — authorization via Presidium, operations via AgentGateway.

**Status:** Draft (revised June 2026)
**Package:** `presidium` (GovernedModelProvider) + `presidium-contrib[agentgateway]` (AgentGateway adapter)
**Milestone:** M2 (authorization) / M3 (AgentGateway adapter, post-execution validation)

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
- Reimplementing rate limiting or cost tracking that AgentGateway already provides

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

**Architecture:** Presidium's `GovernedModelProvider.check()` runs *before* the call reaches AgentGateway. If the check returns DENY, the call never leaves the process. If ALLOW, the call proceeds to AgentGateway which handles routing, rate limiting, and cost tracking.

```
Agent calls LLM
    ↓
GovernedModelProvider.check()     ← Presidium (authorization)
    ↓ ALLOW
AgentGateway                      ← Operations (routing, rate limits, cost)
    ↓ response
GovernedModelProvider.post_check() ← Presidium POST_LLM (M3, output validation)
    ↓
Agent receives response
```

## Design

### Gateway as ModelProvider

```python
class GovernedModelProvider(ModelProvider):
    """LLM gateway that enforces rate limits, cost tracking, and routing."""

    async def chat(
        self,
        messages: list[Message],
        *,
        agent_name: str,
        **kwargs: Any,
    ) -> ModelResponse:
        record = await self.registry.lookup(agent_name)

        # 1. Check rate limits
        await self.rate_limiter.check(agent_name)

        # 2. Check budget
        await self.budget_tracker.check(agent_name)

        # 3. Route to provider
        provider = self.router.select(agent_name, record.capabilities)

        # 4. Execute
        response = await provider.chat(messages, **kwargs)

        # 5. Track cost
        await self.budget_tracker.record(agent_name, response.usage)

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

- Should the gateway support failover (if Anthropic is down, fall back to OpenAI)?
- How does cost tracking persist across restarts? Use Civitas's StateStore?
- Should budget enforcement be per-agent, per-team, or per-organization?
- Integration with Civitas's existing ModelProvider plugins (AnthropicProvider, etc.)?
