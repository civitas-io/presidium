# Vendor research: AgentGateway, 2026-08-24

**Status:** Research complete, feeds directly into the `AgentGatewayClient` tool-side
implementation (`list_tools()`/`call_tool()`) design pass that follows this doc.
**Why now:** before adding two methods to `AgentGatewayClient`, confirm what the *current*
AgentGateway actually does, at the wire level, version level, and security level — not the
snapshot `docs/design/llm-gateway.md`/`mcp-gateway.md` were originally written against. Every
claim below is sourced directly (GitHub releases API, the project's own current docs,
`agentgateway.dev`), not carried over from memory of an earlier version.

---

## 1. Where AgentGateway actually stands today

**Latest release: `v1.4.1`** (2026-07-29), following `v1.4.0` (2026-07-27) — the release that
matters here, since it's a genuinely major version, not an incremental patch. Apache 2.0, Linux
Foundation project, Rust, 4,499 GitHub stars, 339 open issues, active community meetings —
healthy, current, not a stalled project. This confirms `llm-gateway.md`'s own market research
conclusion is still correct: **no second `ToolsGatewayBackend` candidate exists** — AgentGateway
remains the only product doing MCP + A2A routing at Presidium's self-hostable, Python-friendly
bar.

### v1.4.0's real, relevant new features (not an exhaustive changelog — filtered to what touches Presidium's own design)

- **Full support for the MCP `2026-07-28` protocol revision** (the same stateless rewrite
  `civitas-io/fabrica`'s own MCP transport benchmark spike flagged as a real, relevant, unresolved
  question) — see §2 below, this is the single most load-bearing finding in this research pass.
- **Cross App Access / Enterprise-Managed Authorization for MCP** (OAuth Identity Assertion
  Authorization Grant / ID-JAG) — centralized access control brokering, real, new.
- **OAuth token exchange backend authentication** (RFC 8693 + RFC 7523) — lets AgentGateway
  exchange an incoming token for a backend credential.
- **New MCP auth providers**: Microsoft Entra ID (native), Descope, authentik.
- **Standalone mode**: config can now persist to a real database (`sqlite` local / `postgres`
  remote-or-HA) instead of only a flat YAML file; a new `gateways` config replaces the older
  low-level `binds` API, serving LLM/MCP/generic routes and the UI on one port.
- **Gateway API v1.6 support** (breaking change: re-apply CRDs before upgrading, only relevant
  for a Kubernetes deployment, not the standalone binary Presidium would realistically test
  against first).

### A real, HIGH-severity security advisory, fixed in this same release

**[GHSA-mvgg-jvj2-4frq](https://github.com/agentgateway/agentgateway/security/advisories/GHSA-mvgg-jvj2-4frq)**
("Stateful MCP sessions can cross routes and overwrite the authorization policy"), CVSS 8.1,
**fixed in v1.4.0, affects v1.3.1 and all earlier versions**. A session ID reused across two
routes with different `mcpAuthorization` policies and different backends could apply the WRONG
route's policy to the ORIGINAL route's backend connection — a real authorization bypass, not a
theoretical one. **Direct, concrete recommendation for this project**: any real deployment or
test harness built against AgentGateway must pin `>=1.4.0`. Given this project (Presidium) is
itself a governance/authorization product, shipping a design or example that silently tolerates
an unpinned, vul version of its own operations backend would be a real, avoidable gap —
this floor should be stated explicitly wherever AgentGateway is referenced as a dependency, the
same way `civitas>=0.11.3` is pinned specifically (not `>=0.11.0`) in this repo's own
`pyproject.toml` for an analogous "the floor matters, not just the major version" reason.

---

## 2. The load-bearing finding: MCP protocol version compatibility, checked directly, not assumed

`civitas-io/fabrica`'s own `SPIKE-mcp-transport-benchmark.md` flagged that this project's
currently-pinned `mcp==2.0.0` Python SDK still uses the *older*, stateful MCP protocol (confirmed:
its own benchmark harness calls `session.initialize()` on every connect) — and separately noted
that the MCP spec's `2026-07-28` revision removed sessions and the `initialize` handshake
entirely. That raised a real, unresolved question: **can a client built on the older, stateful
`mcp` SDK even talk to a modern AgentGateway `v1.4.x` instance at all?**

**Checked directly against AgentGateway's own "MCP spec compatibility" documentation. Yes —
confirmed, not assumed:**

> "**Older client to newer server**: The client uses the older `initialize` flow, which
> agentgateway continues to support."

AgentGateway performs automatic protocol version negotiation as a deliberate, documented,
default-on feature — "most environments run a mix of MCP versions for the foreseeable future."
An older, stateful client (which is what `mcp==2.0.0`-based code is) talking to a `v1.4.x`
AgentGateway instance is an explicitly supported, first-class path, not a fallback edge case.
**This means the `list_tools()`/`call_tool()` implementation can proceed against the currently
real, pinned `mcp` SDK version without waiting on an SDK upgrade to the newer stateless spec.**

### The wire shape, confirmed directly — and it's the SAME transport GH #26 just shipped

AgentGateway's real Streamable HTTP MCP endpoint behaves like an ordinary, spec-compliant MCP
server from a client's perspective: a client sends `initialize` (no session), AgentGateway
returns an `Mcp-Session-Id` header (AES-256-GCM-encoded backend-pinning state, by default —
`statefulMode: stateless` is available to opt out), and subsequent `tools/list`/`tools/call`
requests carrying that session ID are proxied through to the real, correct upstream MCP server.

**Concretely: `mcp.client.streamable_http.streamable_http_client(url)` — the exact function
`civitas-io/fabrica`'s `MCPClient.connect()` was just extended to use for GH #26 — is directly
reusable, unmodified, against a real AgentGateway MCP endpoint.** No bespoke protocol work is
needed for the MCP half of this implementation; it is the same transport, already tested end to
end against a real server in the GH #26 work. This is a genuine, concrete unblock, and the exact
dependency the `mcp-gateway.md` design doc's own "Open Questions" section named as unresolved
("worth checking whether `list_tools`/`call_tool`'s implementation depends on \[GH #26\] landing
first") — it did, and it has now landed (`civitas` v0.11.3, `fabrica-context` v0.2.0).

---

## 3. A real, previously-underestimated scope finding: `call_tool()` needs TWO client implementations, not one

`mcp-gateway.md`'s "agents as tools" design deliberately makes `call_tool(name, arguments)` the
same method whether `name` resolves to a classic MCP tool or an A2A agent-delegation target. That
uniform method signature is still the right call-site ergonomics — but checked directly against
AgentGateway's own real A2A support, **the two targets are proxied through fundamentally
different wire protocols, not one shared transport**:

- **MCP tools**: real MCP JSON-RPC over Streamable HTTP (§2 above) — the `mcp` SDK already
  covers this, and now speaks the transport AgentGateway itself proxies.
- **A2A agents**: AgentGateway's A2A support (confirmed directly against its own docs) is a
  **pure HTTP reverse proxy** keyed off a route-level `a2a: {}` policy marker, not a unified
  gateway-native API. The actual wire protocol is A2A's own: an agent card served at
  `/.well-known/agent.json` (capabilities, skills, supported modalities), and JSON-RPC-shaped
  methods like `message/stream` for task submission — nothing overlapping with MCP's own
  `tools/list`/`tools/call` shape at all.

**Concrete implication**: implementing `call_tool()`'s agent-delegation path requires a real A2A
client, not an extension of the `mcp` SDK usage that covers the tool path. The official option,
checked directly: **[`a2a-sdk`](https://pypi.org/project/a2a-sdk/)** (from `a2aproject/a2a-python`,
the same org that publishes the A2A spec itself), currently `1.1.2` on PyPI. This is a real,
separate new dependency this work would introduce to `presidium-contrib`, not something already
in place.

**Sequencing implication for the design pass that follows this doc**: the MCP-tool half of
`call_tool()` is the smaller, better-grounded, more immediately buildable piece (reuses a
transport this org already shipped and tested); the A2A-agent half is a real, separate chunk of
work with its own new dependency and its own real end-to-end test needs. These should very likely
be sequenced as two separate, real steps — MCP first — rather than attempted as one combined
change, even though the public `call_tool()` signature stays unified. Worth deciding explicitly
in the design pass, not defaulting into doing both at once.

---

## 4. A real, bigger-than-"two methods" structural gap, confirmed by reading the actual current source

`mcp-gateway.md`/`llm-gateway.md` describe `GovernedModelProvider`/`GovernedToolProvider` as
depending on new `LLMGatewayBackend`/`ToolsGatewayBackend` Protocols (defined in a
`presidium/providers/gateway.py` that doesn't exist yet). Checked directly against the real,
current source before starting any implementation:

- **`presidium/providers/gateway.py` genuinely does not exist.** Confirmed via a direct file
  search — there is no `gateway.py` anywhere in `packages/presidium/src/presidium/providers/`.
- **`GovernedToolProvider`/`GovernedModelProvider` (`providers/tool.py`, `providers/model.py`)
  are, today, pure authorization gates — zero operations-delegation mechanism of any kind.**
  Confirmed by reading both files in full: `check()`/`check_grant()`/`post_check()` only ever
  evaluate policy and emit audit events; neither class holds a reference to any backend, gateway,
  or execution mechanism. There is nothing to "add two methods to" on the Presidium-core side —
  the wiring itself needs to be built, not just AgentGateway's own adapter class.
- **This is separate from, and should not be confused with, the already-real, already-shipped
  `GovernedModelProviderAdapter`/`GovernedToolAdapter`** (`presidium/providers/civitas_adapters.py`,
  P0 item 5 from the 2026-08-22 session) — those wrap a real, *directly-constructed*, in-process
  Civitas `ModelProvider`/`ToolProvider` (e.g., a direct Anthropic client, or a directly-connected
  `MCPTool`), with no external gateway *process* involved at all. `AgentGatewayClient` is a
  fundamentally different deployment shape: delegating the actual operation to a *separate,
  running AgentGateway process* over the network, specifically to get AgentGateway's own
  operational value (rate limiting, cost tracking, cross-provider routing, MCP tool federation,
  A2A routing) that a direct in-process call doesn't provide. Both are real, valid, and
  intentionally different — this doc exists partly to prevent conflating them during the design
  pass.

**Concrete implication**: the real scope of "add `AgentGatewayClient`'s tool-side methods" is at
minimum three layers, not one — (a) the `ToolsGatewayBackend` Protocol itself, (b)
`GovernedToolProvider` gaining a real, optional operations-delegation path that calls it after
authorization succeeds, and (c) `AgentGatewayClient.list_tools()`/`call_tool()` as the concrete
implementation of (a). All three are currently undone.

---

## 5. A real, open architectural question this research surfaces, not previously named

AgentGateway has **its own native MCP authorization layer** — CEL-based, evaluating against
`tools/list`/`tools/call` method invocations, with JWT-claim-based role matching (confirmed
directly against its "MCP authorization" docs). This means a deployment routing tool calls
through AgentGateway could end up with **two independent CEL policy engines** evaluating the same
call: Presidium's own `CelPolicyEngine` (agent registry, trust scores, grants) at `PRE_TOOL`, and
AgentGateway's own tool/prompt/resource-level CEL authz at the proxy layer.

This isn't a new problem invented by this finding — `llm-gateway.md` already states the guiding
principle plainly: *"Presidium handles authorization ... BEFORE calling this client. AgentGateway
handles operations."* But that principle has, until now, only been asserted for the LLM path; it
hasn't been checked against AgentGateway's *own* real MCP authorization feature specifically. The
real, concrete decision the design pass needs to make explicitly (not leave implicit): **should a
Presidium-fronted AgentGateway deployment configure AgentGateway's own MCP authorization as
permissive/allow-all** (Presidium remains the single, real source of truth for the authorization
decision, AgentGateway is pure operations for tool calls specifically), **or is there a real,
named reason to run both** (e.g., defense-in-depth against a caller that reaches AgentGateway
directly, bypassing Presidium entirely)? Both are legitimate; the design pass should pick one and
say why, not leave it as an accidental default.

---

## 6. Summary — what changes for the design pass because of this research

1. **No SDK upgrade is required first.** `mcp==2.0.0`'s stateful client is explicitly, natively
   supported by AgentGateway's own version negotiation. Proceed against the current pin.
2. **The MCP-tool half of `call_tool()` reuses GH #26's real, tested Streamable HTTP transport
   work directly** — a genuine, concrete unblock, not just "probably fine."
3. **The A2A-agent half needs a real, separate, new dependency (`a2a-sdk`) and its own
   implementation path** — bigger and more separate from the MCP half than the original design
   doc's unified `call_tool()` signature implied. Recommend sequencing MCP first, A2A as an
   explicit second step.
4. **Any AgentGateway version referenced in code, docs, or a test fixture from here forward
   should be pinned `>=1.4.0`**, citing GHSA-mvgg-jvj2-4frq directly — not left as "whatever's
   latest" or an unpinned `curl | bash` install.
5. **The real, undone work is three layers, not one**: the `ToolsGatewayBackend` Protocol itself,
   `GovernedToolProvider`'s new operations-delegation path, and `AgentGatewayClient`'s concrete
   implementation — `presidium/providers/gateway.py` does not exist yet and needs to be created,
   not just extended.
6. **A real, previously-unstated architectural decision needs to be made explicitly**: whether
   AgentGateway's own native MCP authorization is disabled (Presidium as sole authority) or run
   in a defense-in-depth role alongside Presidium's — name the choice and the reason.
