# Presidium Server: Requirements

> What the real, self-hostable network governance service (M7) must do.
> Status: Draft
> Milestone: M7 (Presidium Server)
> Depends on: [agent-registry-requirements.md](agent-registry-requirements.md),
> [policy-engine-requirements.md](policy-engine-requirements.md),
> [`civitas-io/fabrica`'s `docs/contracts/managers.md`](https://github.com/civitas-io/fabrica/blob/main/docs/contracts/managers.md)
> (the `PresidiumClient.check_grant()` contract this milestone exists to satisfy)

## Overview

Presidium's governance surface is reachable today in exactly two ways: in-process (a library
call inside the same Python process), or via Civitas's own actor-model transport (Service Mode's
`PolicyEvaluatorServer`/`RegistryServer` GenServers, reachable only by other Civitas agents on the
same bus). **Neither is reachable by an external, non-Civitas system.** `civitas-io/fabrica`'s
`PresidiumClient` Protocol (`check_grant()`) is fully specified and implementation-ready, but has
nothing real to call.

Presidium Server closes that gap: a real, self-hostable process exposing governance decisions over
REST+mTLS to any authenticated caller — Civitas-based or not.

**Not the same thing as M6 ("Cloud").** M6 is the commercial, multi-tenant SaaS offering. M7 is the
underlying OSS building block: can Presidium run as its own addressable, self-hosted,
single-tenant process at all. M6 would eventually run a managed, multi-tenant deployment of what
M7 builds — not the reverse.

---

## Functional Requirements

### FR-1: `check_grant` — the one, real, concrete consumer this milestone is scoped around

**FR-1.1**: The server MUST expose `POST /v1/check_grant`, satisfying `civitas-io/fabrica`'s
`PresidiumClient.check_grant(agent_id, action, scope) -> GrantResult` contract exactly: request
body `{"agent_id": str, "action": str, "scope": dict}`; response body
`{"decision": "allow"|"deny"|"require_approval", "reason": str | null, "approval_context": dict | null}`.

**FR-1.2**: `agent_id` MUST be resolved via `AgentRegistry.lookup_by_id()`. An unresolvable
`agent_id` MUST return `{"decision": "deny", "reason": "Agent not found in registry"}` — never a
5xx, never an exception surfaced to the caller. Matches `GovernedToolProvider.check()`'s existing
"agent not found → deny" behavior.

**FR-1.3**: `action` (a free-form string Presidium interprets, e.g. `"code_mode"`,
`"skill_run:pdf-extract"`) MUST map onto `ActionRequest` as follows (**"Option 2", decided
2026-08-22, refined from an initial sketch that required a bespoke suffix-stripping rule**):
  - `ActionRequest.resource` = `action`, **verbatim, unmodified** — the whole original string,
    colon included where present.
  - `ActionRequest.action` = the fixed, generic verb `"invoke"` — matching the existing convention
    already used elsewhere in Presidium (`GovernedToolProvider.check()`'s own default
    `action: str = "invoke"`, `AgentGatewayClient`'s LLM calls).
  - Rationale: lets CEL policies distinguish categories via `request.resource.startsWith(
    "skill_run:")` (govern all skill runs) or exact-match a specific one
    (`request.resource == "skill_run:pdf-extract"`), without inventing a translation/lookup table
    for category names that wouldn't generalize to action strings not yet invented.

**FR-1.4**: `scope` (Fabrica's own cross-surface `Scope` type, also used by `MemoryStore` and
usage-ledger span attributes) MUST be serialized into `ActionRequest.parameters` so CEL policies
MAY reference it (e.g. `request.parameters.tenant_id`) — Presidium does not interpret `scope`
itself, matching Fabrica's own "opaque to the caller of `check_grant`" framing.

**DONE, 2026-08-24 -- a real, previously-unfixed gap.** This requirement was documented from the
start but never actually implemented: `PresidiumGatewayAgent.handle_call()` read `agent_id`/
`action` from the request body but silently discarded `scope` entirely, and
`GovernedToolProvider.check_grant()`/`check()`/`check_resource()` had no `parameters` parameter
at all to receive it -- `ActionRequest.parameters` could only ever be `{}` on this path, even
though the CEL engine's own activation already exposed `request.parameters` (it just had
nothing in it). Fixed: all three methods gained an additive, optional `parameters: dict[str,
Any] | None = None` (threaded through the shared `_evaluate()` helper); the HTTP handler now
reads `payload.get("scope")`, validates it's a dict if present (fail-closed DENY otherwise, not
a 5xx), and passes it straight through. Verified end to end, not just at the unit level: real
tests prove a CEL policy referencing `request.parameters.tenant_id` sees the value that arrived
in the HTTP request body's `scope` field.

**FR-1.5**: On `PolicyDecision.REQUIRE_APPROVAL`, the server MUST return
`{"decision": "require_approval", ...}` **immediately, without blocking** on approval resolution.
This is a real, deliberate divergence from `GovernedToolProvider.check()`'s existing behavior
(which blocks synchronously on `ApprovalService.request_approval()`) — see FR-2.

**FR-1.6**: `approval_context` (when `decision == "require_approval"`) is opaque to Fabrica by its
own contract ("passed through to Civitas's durable-suspension mechanism... this contract does not
interpret it") — Presidium defines its own shape: at minimum `policy_name`, `reason`, `approvers`
from the underlying `PolicyResult`.

**Known, honest limitation, not hidden**: this milestone returns `require_approval` as a value but
does **not** yet provide a network-reachable way to *resolve* it (FR-4, approval request/list/decide,
is explicitly deferred — see "Out of Scope"). A deployment relying on `REQUIRE_APPROVAL` policies
at the `check_grant` boundary needs that deferred piece built too, or should avoid
`REQUIRE_APPROVAL` policies here until then.

### FR-2: `GovernedToolProvider.check_grant()` — a real, new capability in `presidium` core, not just the server

**FR-2.1**: `presidium` core MUST gain a new method, `GovernedToolProvider.check_grant(agent_name,
tool, action="invoke") -> PolicyResult`, sharing the same registry-lookup + policy-evaluation +
audit-emission logic as the existing `check()` via a private helper — but returning immediately on
`PolicyDecision.REQUIRE_APPROVAL` instead of calling `ApprovalService.request_approval()`.

**FR-2.2**: This MUST be a real, additive, reusable capability — not server-specific glue code.
Any caller with its own suspend/resume mechanism (Civitas's durable suspension is the first real
one, but not necessarily the only one) uses `check_grant()` instead of `check()`.

**FR-2.3**: `check()`'s own existing behavior (block on `REQUIRE_APPROVAL`) MUST NOT change —
`check_grant()` is a new, parallel method, not a modification of `check()`'s contract.

### FR-3: Transport security — mTLS, real and shippable now, not blocked on SPIRE

**FR-3.1**: The server MUST support mTLS via Civitas's own, already-real, already-tested
`civitas.gateway` machinery (`GatewayConfig.tls_cert`/`tls_key`/`tls_ca_cert`/
`client_cert_mode="required"`, `civitas.gateway.mtls.require_client_cert` middleware).

**FR-3.2**: **Real, important clarification (found 2026-08-22, corrects an earlier assumption)**:
Civitas's own mTLS is **X.509 subject-DN allowlist based** (`CIVITAS_GATEWAY_MTLS_ALLOWED_DNS`) —
a completely separate mechanism from `AgentRecord.public_key`'s raw Ed25519 verify keys. These are
two different identity layers with two different jobs:
  - mTLS answers: "is this HTTP request from a legitimate calling *service* at all?" (coarse,
    transport-level, one cert per trusted calling service — e.g. "fabrica-production").
  - `AgentRecord.public_key` answers: "is this claim really attributable to *this specific
    agent*?" (fine-grained, per-agent, used for signature verification/non-repudiation — not TLS).
  They MUST NOT be conflated. mTLS does **not** need to wait on `presidium-contrib[spiffe]`
  (real SPIRE-issued SVIDs) — it can ship now with one simple, real, self-issued private CA.

**FR-3.3**: The operator MUST supply the trust anchor (`tls_ca_cert`) as a dedicated private CA —
never a public or broad CA (Civitas's own `mtls.py` docstring already states this; repeated here
because it's load-bearing for this milestone specifically).

### FR-4: `GET /health` — minimal, not Civitas's full topology introspection

**FR-4.1**: The server MUST expose a real liveness check at `GET /health`.

**FR-4.2**: **Deliberately NOT** using `GatewayConfig.topology_agent` (which auto-registers seven
read routes — `/topology`, `/agents`, `/agents/{name}`, `/agents/{name}/mailbox`, `/snapshot`,
`/metrics`, `/processes` — plus four write routes — suspend/resume/restart/mailbox-inject). A
security product's own network-facing API should have the smallest attack surface consistent with
its real job, not everything that's convenient by default. `/health` is a single, explicit,
purpose-built route.

### FR-5 (Deferred to a later milestone): Registry, approval, credential endpoints

**FR-5.1**: Registry CRUD + grant management, approval request/list/decide, and credential
resolution are designed conceptually (per the original M7 scope) but **not built in this first
cut** — nothing concretely calls them over a network yet, matching "ship the default, revisit if
forced." Real, scoped follow-up, not abandoned.

---

## Non-Functional Requirements

### NFR-1: Fail-closed across the network boundary

An unreachable or erroring server MUST be something the *client* can safely treat as `deny`
without the server needing to do anything special — Fabrica's own contract already assumes this
("never raises for a Presidium-unreachable condition"). The server's only job is to be honest
about its own health (FR-4), not paper over outages.

### NFR-2: Reuse real, tested infrastructure — this is a transport skin, not a rewrite

No new HTTP/TLS/routing framework. `civitas.gateway.HTTPGateway` (mature, 91–100% covered across
its own submodules) is the transport layer in full. `GovernedRuntime`'s existing composition
(policy engine, registry, approval, credentials) is the implementation behind the one real
endpoint. This milestone adds one new `AgentProcess` subclass and one new `presidium` core method
— not a second server framework.

### NFR-3: Default-deny is a real, pending change to core semantics — not assumed done here

**Direction decided, implementation deferred** (see `docs/vision/roadmap.md`'s own P1 entry):
`CelPolicyEngine`'s no-rule-matched case currently defaults to `ALLOW`. A real implementation
attempt to flip this to `DENY` was made and reverted the same session it was proposed, after it
broke 24 existing tests — confirmed to need its own dedicated design pass (every existing
example/test policy assumes implicit allow-by-default; none declare an explicit terminal ALLOW
rule). **`check_grant()`'s behavior today reflects the current, real, ALLOW-on-no-match
semantics** — this doc does not pretend otherwise. When default-deny ships, `check_grant()`
inherits the new behavior automatically (it delegates to the same `CelPolicyEngine`), with no
changes needed to this milestone's own code.

---

## Design Decisions (Resolved)

| Decision | Resolution | Rationale |
|---|---|---|
| Distributed GenServer mesh (Option B) vs. wrap `GovernedRuntime` as one agent (Option A) | **Option A** | `check_grant` needs registry lookup → policy eval → approval handling *composed together* — `GovernedRuntime.tool_provider` (via the new `check_grant()`) already does this correctly, in-process, tested. Recomposing it from separately-deployed `PolicyEvaluatorServer`/`RegistryServer` GenServers would mean re-deriving orchestration logic that already works, for no immediate benefit. Those GenServers remain valid for a *later*, separate, truly-distributed deployment topology — not blocked by this decision. |
| Fabrica `action` → `ActionRequest` mapping | **Option 2, refined**: `resource = action` verbatim, `action = "invoke"` fixed | See FR-1.3. Rejected the initial sketch (splitting `"skill_run:skill_name"` into `resource="skill:..."`, `action="run"` via suffix-stripping) as too bespoke to generalize. |
| `REQUIRE_APPROVAL` handling | New `check_grant()` method, non-blocking | `check()`'s existing blocking behavior doesn't fit Fabrica's own suspend/resume model. See FR-2. |
| mTLS key material | Civitas's own X.509 DN-allowlist mTLS, a private CA — **not** `AgentRecord.public_key`, **not** blocked on `presidium-contrib[spiffe]` | See FR-3.2. Two genuinely different identity layers; conflating them was an earlier, corrected assumption. |
| `/health` route shape | Minimal, explicit, hand-written — not `GatewayConfig.topology_agent`'s auto-registered 11 routes | Smallest attack surface consistent with the real job. |
| Package shape | `presidium_contrib.server` module, `presidium-contrib[server]` extra (needs `civitas[http]`) | See [`presidium-server.md`](presidium-server.md)'s own Architecture section for the full reasoning. |

## Out of Scope (M7, this first cut)

- Registry CRUD, approval request/list/decide, credential resolution over the network (FR-5;
  designed, not built).
- Implementing the default-deny direction itself (NFR-3; recorded, deferred, tracked separately).
- `presidium-contrib[spiffe]` (real SPIRE-issued SVIDs) — a real, separate, later upgrade to the
  *agent-level* identity story, not required for this milestone's mTLS. **Shipped 2026-08-24**
  (`docs/design/spiffe-vendor-research-2026-08.md`) — still genuinely separate from and does not
  touch this milestone's own mTLS, confirming the boundary stated here was correct.
- A true distributed GenServer mesh for `check_grant` (Option B) — real future value, not needed
  for the first real consumer.
