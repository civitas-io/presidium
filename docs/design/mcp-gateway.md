# Design: MCP Gateway

> Governed tool access — authorization + post-execution validation via Model Context Protocol
> and agent-to-agent (A2A) delegation, both through a pluggable gateway backend.

**Status:** Draft (revised 2026-07-07 — generalized to a pluggable `ToolsGatewayBackend` Protocol
covering both MCP tools and A2A agent delegation with a uniform call shape; see changelog below)
**Package:** `presidium` (`GovernedToolProvider` + new `ToolsGatewayBackend` Protocol) +
`presidium-contrib` (MCP governance reference impl + backend adapters)
**Milestone:** M2 (authorization) / M3 (post-execution, tool poisoning, PII masking) / M3+ (backend
pluggability + agents-as-tools, this revision)

> **2026-07-07 changelog:** two changes. (1) Extracted the operations dependency into a
> `ToolsGatewayBackend` Protocol, matching `llm-gateway.md`'s `LLMGatewayBackend` — AgentGateway
> remains the only backend that implements it today (see §"Pluggable backends" below; no other
> researched product does MCP + A2A routing with the self-hostable, Python-friendly profile
> Presidium wants, so unlike the LLM side there is currently no second candidate, only a documented
> gap). (2) Scoped in "agents as tools": `call_tool()` is deliberately the same method whether the
> target is a classic MCP tool or another agent reached via A2A — see §"Agents as tools" below.
> **Inbound exposure (civitas agents discoverable/callable by external A2A clients) is an explicit
> non-goal for this revision**, not a silent omission — see Non-Goals.

## Problem Statement

MCP (Model Context Protocol) gives agents access to external tools — databases, APIs, file systems, code execution. Without governance, any agent can use any tool. There's no access control, no audit trail, no protection against tool poisoning, and no validation of tool outputs for sensitive data leakage.

## Goals

1. Grant-based tool access control via CEL policies (Presidium `PRE_TOOL`)
2. Post-execution output validation via `POST_TOOL` stage (M3) — PII detection, result filtering
3. Tool poisoning detection — hash-based fingerprinting of tool descriptions/parameters
4. Credential redaction from tool call parameters before audit logging
5. Output PII masking — detect and redact sensitive data in tool results before returning to agent
6. Audit log all tool interactions with governance context
7. **Agents as tools (outbound)** — a civitas agent can `call_tool()` another agent (via A2A)
   through the same governed path as a classic MCP tool call, with the same grant/policy/audit
   treatment (M3+, this revision)

## Non-Goals

- MCP server implementation — Civitas handles MCP client integration
- Tool discovery — agents get tools through the gateway, not by scanning
- Content validation (hallucination, factual accuracy) — separate concern (NeMo Guardrails, Guardrails AI)
- **Inbound A2A exposure.** Making a civitas agent discoverable and callable BY external A2A
  clients (other agent frameworks, other AgentGateway deployments) requires civitas to speak the
  A2A *server* role, not just consume it as a client — that's a real, separate feature (likely a
  civitas-side capability, not just a Presidium adapter) and is explicitly deferred, not silently
  dropped. Tracked as a fast-follow once outbound is built and proven.

## Design

### Pluggable backends: the `ToolsGatewayBackend` Protocol

Mirrors `llm-gateway.md`'s `LLMGatewayBackend` — `GovernedToolProvider` depends on a `Protocol`,
not a specific product:

```python
class ToolsGatewayBackend(Protocol):
    """Operations backend for GovernedToolProvider: MCP tool + A2A agent-delegation routing.

    Presidium owns authorization (grants, tool ACLs, CEL policy) and always runs it BEFORE this is
    called. The backend resolves `name` to whichever transport applies (MCP server or A2A peer) —
    the caller does not need to know or care which.
    """

    async def list_tools(self, *, agent_name: str | None = None) -> list[dict[str, Any]]: ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        agent_name: str | None = None,
    ) -> dict[str, Any]: ...

    async def health(self) -> bool: ...
```

**Current adapter status, 2026-08-24 -- MCP tool side DONE, A2A side deliberately deferred.**
All three layers named in the vendor research below are now real, shipped code:
`presidium/providers/gateway.py` (`LLMGatewayBackend`, `ToolsGatewayBackend`,
`GatewayModelProvider`, `GatewayToolProvider`), `GovernedToolProvider`/`GovernedModelProvider`
gaining `check_resource()`/`post_check_resource()` (verbatim-resource variants of `check()`/
`post_check()`, needed for the `agent:<name>` namespace, not just `tool:<name>`), and
`AgentGatewayClient.list_tools()`/`call_tool()` -- real MCP `tools/list`/`tools/call` over
Streamable HTTP, verified end to end against a real running MCP server (not mocked;
`tests/integration/test_agentgateway_mcp_real_server.py`, 5 tests). `delegate_to_agent()` exists
on both `AgentGatewayClient` and `GatewayToolProvider` but the client's own implementation
raises `NotImplementedError` explicitly -- the A2A half needs a real `a2a-sdk` dependency and its
own end-to-end test, deliberately sequenced as a separate follow-up (decision 3 below), not
silently stubbed to look done.

**2026-08-24 vendor research, before implementation starts:**
[`docs/design/agentgateway-vendor-research-2026-08.md`](agentgateway-vendor-research-2026-08.md) —
real, current findings against AgentGateway `v1.4.1`, checked directly against its own docs/
releases/security advisories, not carried over from this doc's original snapshot. Highlights:
(1) a real, HIGH-severity security advisory (GHSA-mvgg-jvj2-4frq, session/authz confusion across
routes) is fixed in `v1.4.0` — any future pin must be `>=1.4.0`; (2) the MCP version-negotiation
question this doc's own Open Questions section raised is resolved — AgentGateway explicitly
supports an older, stateful `mcp` SDK client (what this org currently has) against its modern
endpoint, and that endpoint speaks the exact Streamable HTTP transport GH #26 just shipped, so the
MCP-tool half of `call_tool()` needs no new transport work; (3) the A2A-agent half is a genuinely
separate, bigger piece of work than the unified `call_tool()` signature implies — a different wire
protocol entirely, needing a new `a2a-sdk` dependency, not an extension of the MCP path; (4) the
real, undone work is three layers, not one — `presidium/providers/gateway.py` (the
`ToolsGatewayBackend` Protocol itself) does not exist yet, `GovernedToolProvider` has zero
operations-delegation mechanism today (confirmed by reading its current source), and
`AgentGatewayClient` is only the third, outermost layer.

No second `ToolsGatewayBackend` candidate is proposed here, unlike the LLM side. The market
research behind `llm-gateway.md`'s backend table did not turn up another product that does MCP +
A2A routing with a self-hostable, Python-friendly profile — the ~10 MCP-gateway projects noted in
§"MCP Governance Landscape" below (mcp-zero, mcp-guardian, etc.) informed *pattern* choices, not a
second full backend. This is a documented gap, revisited if a concrete need or customer signal
surfaces one. **2026-08-24 confirmation**: `v1.4.1`'s own release notes/changelog were checked
directly and this conclusion still holds — no new competing product has emerged.

### Agents as tools (outbound)

`call_tool(name, arguments)` is deliberately the same *conceptual* operation whether `name`
resolves to a classic MCP tool (`"database.query"`) or another agent reached via A2A
(`"specialist_researcher"`) -- the same grant model, the same `PRE_TOOL`/`POST_TOOL` CEL stages,
the same audit trail, the same tool-poisoning-style change detection and credential redaction
apply to both. A policy author never writes separate rules for "calling a tool" vs. "delegating to
an agent."

**Design decisions, 2026-08-24, made directly from `agentgateway-vendor-research-2026-08.md`'s
findings, resolving what was previously left TBD:**

1. **Grant/resource shape, resolved**: `tool:<name>` for an MCP tool (unchanged, matches
   `GovernedToolProvider.check()`'s existing `f"tool:{tool}"` convention exactly), and
   **`agent:<name>`** for an A2A delegation target -- parallel shape, same `action` parameter
   handling `check()` already has (default `"invoke"`), not baked into the resource string
   itself. Chosen for consistency with the one naming pattern this codebase already has, not a
   new one invented for this case.
2. **One conceptual operation, two concrete Python methods, not one polymorphic method** -- a real
   correction to this doc's original framing, forced by vendor-research finding 4: AgentGateway's
   A2A support is a genuinely different wire protocol (a pure HTTP reverse proxy, agent cards,
   `message/stream`) from its MCP support (real MCP JSON-RPC over Streamable HTTP), needing a
   separate `a2a-sdk` client under the hood. A single Python method cannot construct the correct
   `tool:`/`agent:` authorization resource string without already knowing which kind of target
   it's calling -- so the **caller** states the target kind explicitly (they already know
   semantically whether they're calling a tool or delegating to an agent), and the "one path"
   guarantee is preserved at the *policy/audit* level (both funnel through the same
   `GovernedToolProvider.check()`/`post_check()` calls and the same underlying
   `ToolsGatewayBackend` health/lifecycle), not by hiding the distinction from the caller
   entirely. Concretely: `GatewayToolProvider.call_tool(name, arguments)` for MCP tools,
   `GatewayToolProvider.delegate_to_agent(agent_name, arguments)` for A2A targets -- see
   `providers/gateway.py` below.
3. **Sequencing, resolved**: MCP-tool support ships first (real, immediately buildable -- reuses
   GH #26's already-tested Streamable HTTP transport directly). A2A delegation is a real, explicit
   second phase, needing the new `a2a-sdk` dependency and its own end-to-end test against a real
   A2A agent -- not attempted in the same change.
4. **`list_tools()` is authorization-exempt, by design, not an oversight**: listing available
   tools doesn't execute anything, so it passes straight through to the backend with no
   `PRE_TOOL` check -- matching the existing precedent that discovery and invocation are different
   trust boundaries (an agent can see a tool exists without being granted to call it; the CEL
   policy is evaluated at `call_tool()`/`delegate_to_agent()` time, not at listing time).
5. **AgentGateway's own native MCP authorization (CEL-based tool ACLs, confirmed real in the
   vendor research) is configured permissively/allow-all for calls arriving via this integration
   in v1** -- Presidium remains the sole authorization authority for this path, consistent with
   `llm-gateway.md`'s already-stated principle applied explicitly to the MCP side for the first
   time. This is a deployment/configuration recommendation for whoever runs the real AgentGateway
   instance, not something enforceable from the Python client alone. **Named as a real, deliberate
   choice with a real, named revisit trigger**: if an AgentGateway deployment is ever reachable by
   a caller OTHER than through Presidium's own governed path, its own authorization becomes a
   legitimate, real defense-in-depth layer worth enabling -- not a hypothetical, just not this
   integration's default assumption for v1.

This is scoped to **outbound only** -- a civitas agent calling out through the gateway. See
Non-Goals for the deferred inbound direction.

### `GatewayToolProvider`/`GatewayModelProvider` -- the real composition shape

A third, distinct integration point in this codebase, alongside the two that already exist --
worth naming clearly so a future reader doesn't conflate them (this confusion is exactly what
`agentgateway-vendor-research-2026-08.md` §4 found and flagged):

1. `GovernedModelProvider`/`GovernedToolProvider` (`providers/model.py`/`providers/tool.py`) --
   pure authorization gates. `check()`/`post_check()` only. No backend of any kind.
2. `GovernedModelProviderAdapter`/`GovernedToolAdapter` (`providers/civitas_adapters.py`) -- wraps
   a real, *directly-constructed, in-process* Civitas `ModelProvider`/`ToolProvider`. No external
   gateway process. Already real, shipped (P0 item 5, 2026-08-22).
3. **New: `GatewayModelProvider`/`GatewayToolProvider` (`providers/gateway.py`, this design)** --
   wraps an `LLMGatewayBackend`/`ToolsGatewayBackend` (AgentGateway today; a real, running,
   separate process reached over the network). Same check-then-delegate-then-post_check
   composition pattern as (2), applied to a gateway backend instead of a direct Civitas provider
   -- reusing an established pattern, not inventing a new one, but genuinely a different
   construction path since the backend Protocols return raw OpenAI-style/MCP-style dicts, not
   civitas's `ModelResponse`/`ToolProvider` shapes.

```python
class LLMGatewayBackend(Protocol):
    """Already specified in llm-gateway.md -- AgentGatewayClient's real chat()/list_models()/
    health() already satisfy this shape exactly, structurally, with zero changes needed."""
    async def chat(
        self, messages: list[dict[str, str]], *, model: str | None = None,
        agent_name: str | None = None, **kwargs: Any,
    ) -> dict[str, Any]: ...
    async def list_models(self) -> list[dict[str, Any]]: ...
    async def health(self) -> bool: ...


class ToolsGatewayBackend(Protocol):
    async def list_tools(self, *, agent_name: str | None = None) -> list[dict[str, Any]]: ...
    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, agent_name: str | None = None,
    ) -> dict[str, Any]: ...
    async def delegate_to_agent(
        self, agent_name_target: str, arguments: dict[str, Any], *, agent_name: str | None = None,
    ) -> dict[str, Any]: ...
    async def health(self) -> bool: ...


class GatewayToolProvider:
    """Composes a GovernedToolProvider (authorization) with a ToolsGatewayBackend (operations).
    Bound to one agent_name at construction, matching the civitas_adapters.py precedent."""

    def __init__(
        self, *, backend: ToolsGatewayBackend, tool_provider: GovernedToolProvider, agent_name: str,
    ) -> None: ...

    async def list_tools(self) -> list[dict[str, Any]]:
        """No PRE_TOOL check -- discovery, not invocation. See decision 4 above."""
        return await self._backend.list_tools(agent_name=self._agent_name)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """resource = f"tool:{name}" -- check, delegate, post_check. Raises PolicyDeniedError
        on a PRE_TOOL or POST_TOOL deny, matching GovernedToolAdapter's existing convention."""
        ...

    async def delegate_to_agent(self, agent_name_target: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """resource = f"agent:{agent_name_target}" -- otherwise identical shape to call_tool()."""
        ...
```

### Access Control

Tool access is determined by agent capabilities in the registry:

```yaml
# Registry entry:
agents:
  - name: data-analyst
    capabilities:
      - "tool:database:read"
      - "tool:spreadsheet:*"
    # Cannot access: tool:filesystem:*, tool:code_execution:*

# MCP Gateway enforces:
# data-analyst calls database.query() → ALLOW (has tool:database:read)
# data-analyst calls filesystem.write() → DENY (no tool:filesystem:* capability)
```

### Tool Poisoning Detection

```python
@dataclass
class ToolSnapshot:
    """Captures tool state at approval time."""
    name: str
    description_hash: str
    parameters_hash: str
    approved_at: datetime
    approved_by: str

class PoisoningDetector:
    """Detects tools that have changed since approval."""

    async def check(self, tool: ToolDefinition) -> PoisoningResult:
        snapshot = await self.store.get_snapshot(tool.name)
        if snapshot is None:
            return PoisoningResult(status="unapproved")

        if hash(tool.description) != snapshot.description_hash:
            return PoisoningResult(status="description_changed")

        if hash(tool.parameters) != snapshot.parameters_hash:
            return PoisoningResult(status="parameters_changed")

        return PoisoningResult(status="clean")
```

### Credential Redaction

Before logging tool call parameters, redact sensitive values:

```python
REDACTION_PATTERNS = [
    r"(?i)(api[_-]?key|token|secret|password|credential)\s*[:=]\s*\S+",
    r"(?i)bearer\s+\S+",
    r"sk-[a-zA-Z0-9]+",  # OpenAI keys
]
```

## Post-Execution Output Validation (M3)

The `POST_TOOL` evaluation stage runs after tool execution, before the result is returned to the agent:

```
Agent calls tool
    ↓
GovernedToolProvider.check()       ← PRE_TOOL (authorization, grant check)
    ↓ ALLOW
Tool executes                      ← MCP call
    ↓ result
GovernedToolProvider.post_check()  ← POST_TOOL (output validation)
    ↓ ALLOW/DENY/REDACT
Agent receives result
```

### Output PII Masking

Tool results may contain sensitive data (SSNs, credit cards, API keys, emails) that the agent doesn't need and shouldn't persist in context. Post-execution PII masking detects and redacts before the result reaches the agent:

```python
# CEL policy example for POST_TOOL
- name: mask-pii-in-results
  stage: post_tool
  expression: >
    result.contains_pii == true
  decision: require_approval
  reason: "Tool result contains PII — review before returning to agent"
  priority: 80
```

PII detection itself is not CEL — it uses regex patterns or an external service (Microsoft Presidio, AWS Comprehend). The CEL policy decides *what to do* when PII is detected (deny, redact, require approval). The detection is a context enrichment step before policy evaluation.

### Result Size Limits

Unbounded tool results can exhaust agent context windows:

```python
- name: limit-result-size
  stage: post_tool
  expression: >
    result.size_bytes > 100000
  decision: deny
  reason: "Tool result exceeds 100KB limit"
  priority: 70
```

## MCP Governance Landscape

Research (June 2026) identified 10+ MCP gateway projects addressing tool governance. Key patterns Presidium adopts:

| Pattern | Source | Presidium approach |
|---|---|---|
| Default-deny tool access | mcp-zero, mcp-gov | `enforce-grants` policy at priority 100 |
| Tool fingerprinting | mcp-guardian | Hash-based `ToolSnapshot` in contrib |
| Output PII masking | mcp-zero (Presidio) | `POST_TOOL` stage + PII detection enrichment |
| Shadow/audit mode | mcp-guardian | `advisory` enforcement mode |
| Credential redaction | mcp-zero, mcp-guardian | Regex-based parameter redaction before audit |

AgentGateway (Linux Foundation) provides native MCP routing with CEL policies, and is the sole
`ToolsGatewayBackend` implementation (see "Pluggable backends" above — the adapter needs
`list_tools`/`call_tool` added to actually reach this, tracked as an issue). The
`presidium-contrib[agentgateway]` adapter delegates MCP + A2A routing to AgentGateway while
Presidium owns authorization and post-execution validation.

## Open Questions

- Should tool approval be per-agent or global? (Lean per-agent — matches grant model)
- How do we handle tools that legitimately change (version updates)? (Re-approval workflow with diff)
- PII detection backend: built-in regex patterns vs. external service (Presidio)? (Start regex, Presidio as contrib adapter)
- Should POST_TOOL be able to *modify* results (redact inline) or only ALLOW/DENY? (Lean toward ALLOW/DENY/REDACT as a third decision type for post-execution)
- Integration with Civitas's existing MCP module?
- **What does a grant look like for an agent-target, not a tool-target?** `tool:database:read` is
  natural for MCP tools; an A2A delegation target needs a grant shape too (e.g.
  `agent:specialist_researcher:invoke`?) — needs to be pinned down when `call_tool()`'s agent-target
  path is actually implemented, not just designed.
- ~~**Civitas issue #26** ("MCP client only supports stdio/sse transport — no Streamable HTTP") may
  block reaching AgentGateway's MCP proxy over its preferred Streamable HTTP transport — worth
  checking whether `list_tools`/`call_tool`'s implementation depends on that landing first.~~
  **Resolved, 2026-08-24**: GH #26 is closed (`civitas` v0.11.3, `fabrica-context` v0.2.0), and it
  was a real prerequisite, not a false alarm — AgentGateway's MCP endpoint is genuine Streamable
  HTTP, confirmed directly against its own docs. See
  [`agentgateway-vendor-research-2026-08.md`](agentgateway-vendor-research-2026-08.md) §2 for the
  full confirmation, including that no `mcp` SDK upgrade is needed first (AgentGateway explicitly
  supports the older, stateful client this org's `mcp==2.0.0` pin uses).
