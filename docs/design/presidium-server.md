# Design: Presidium Server

> A real, self-hostable network governance service — REST+mTLS, reusing Civitas's own gateway.

**Status:** Draft (2026-08-22)
**Package:** `presidium-contrib` (`presidium_contrib.server`, new module) + `presidium` core (one new
`GovernedToolProvider` method)
**Milestone:** M7
**Requirements:** [presidium-server-requirements.md](presidium-server-requirements.md)

## Problem Statement

Presidium's governance surface is reachable in exactly two ways today: in-process (library calls
inside one Python process), or via Civitas's own actor transport (Service Mode's
`PolicyEvaluatorServer`/`RegistryServer`, reachable only by other Civitas agents). Neither is
reachable from outside a single Civitas process. `civitas-io/fabrica`'s `PresidiumClient.
check_grant()` — a fully-specified, implementation-ready contract — has nothing real to talk to.

## Goals

1. A real, self-hostable process exposing `check_grant()` over REST+mTLS, satisfying Fabrica's own
   contract exactly.
2. Reuse real, already-tested infrastructure end to end — `civitas.gateway.HTTPGateway` for
   transport/mTLS, `GovernedRuntime`'s existing composition for governance logic. No new server
   framework, no new TLS handling.
3. A minimal, deliberately small network attack surface — one real endpoint plus a health check,
   not everything M7's original scope imagined, until something concretely needs the rest.

## Non-Goals (this milestone)

- ~~Registry CRUD~~ over the network — **DONE, 2026-08-24**, see "Deferred: the fuller REST
  surface" below for the full real detail (now shipped, not deferred). Approval
  request/list/decide, credential resolution over the network remain real, designed intents,
  not built.
- A true distributed GenServer mesh recomposing `PolicyEvaluatorServer`/`RegistryServer` for
  `check_grant` — `GovernedRuntime`'s existing in-process composition already does this correctly.
- `presidium-contrib[spiffe]` (real SPIRE SVIDs) — a separate, later upgrade to agent-level
  identity, not required for this milestone's service-level mTLS. **Shipped 2026-08-24** — still
  genuinely separate from this milestone's own mTLS, as predicted here.
- Implementing the default-deny direction for `CelPolicyEngine`'s no-match case — a real, decided,
  but separately-tracked piece of work (see `docs/vision/roadmap.md`).

---

## Architecture

```
                              ┌─────────────────────────────────┐
   External caller            │      civitas.gateway.HTTPGateway │
   (e.g. civitas-io/fabrica)  │  ┌─────────────────────────────┐  │
   ── mTLS (real X.509,   ──▶ │  │ require_client_cert          │  │
      private CA)             │  │  (Civitas's own, 98% covered)│  │
                              │  └──────────────┬──────────────┘  │
                              │                 ▼ dispatch (bus)   │
                              └────────┬────────────────────────┘
                                       │  {"__op__": "check_grant", ...}
                                       ▼
                         ┌───────────────────────────────┐
                         │   PresidiumGatewayAgent        │
                         │   (new, presidium_contrib.server)│
                         │   handle() dispatches on __op__ │
                         └───────────────┬────────────────┘
                                         │ calls
                                         ▼
                         ┌───────────────────────────────┐
                         │   GovernedRuntime               │
                         │   (existing, unmodified)        │
                         │   .tool_provider.check_grant()  │  ← new method (FR-2)
                         └───────────────┬────────────────┘
                                         │ delegates to (existing, unmodified)
                     ┌───────────────────┼───────────────────┐
                     ▼                   ▼                   ▼
              AgentRegistry        CelPolicyEngine      ApprovalService
              (lookup_by_id)       (evaluate)           (NOT called on
                                                          REQUIRE_APPROVAL —
                                                          see FR-1.5/FR-2)
```

**The load-bearing design choice**: `PresidiumGatewayAgent` is a thin translation layer only. It
does not reimplement lookup/evaluation/approval logic — it constructs a `GovernedRuntime` (or
receives one) and calls the new `check_grant()` method on its `tool_provider`. Everything below
that line is existing, already-tested code, unmodified.

### Why not the separately-deployed `PolicyEvaluatorServer`/`RegistryServer` GenServers?

They remain real and valid — for a genuinely distributed deployment where policy evaluation and
registry lookups run as independently-scaled processes. But `check_grant` needs registry lookup →
policy evaluation → (non-blocking) approval handling *composed together*, and that composition
already exists, correctly, as `GovernedRuntime`'s own object graph. Re-deriving it by having
`PresidiumGatewayAgent` call the two GenServers over the bus (ask → ask) would mean maintaining two
parallel implementations of the same orchestration for no immediate benefit. If a real, later need
emerges for independently-scaled policy evaluation at high QPS (see M8, Performance Research),
that's the moment to build the distributed version — not before.

---

## Data Model

### Real, implemented (2026-08-22) — this section reflects the shipped code, not a sketch

**A real design correction found during implementation, corrects the two subsections below as
they originally read**: the original sketch had `PresidiumGatewayAgent` dispatch on a single
`message.payload["__op__"]` marker injected via each route's `payload_extra` — modeled on how
Civitas's own auto-registered topology routes work. Verified directly against
`civitas.gateway.router.RouteTable.from_config()` (the real parser for user-declared `routes:`
config, confirmed by reading the source and then confirming live against a real running gateway)
that **`payload_extra` is never populated for ordinary, user-declared routes** — it is exclusively
set by Civitas's own internal `_build_topology_routes()` construction, not a general-purpose
mechanism exposed through `GatewayConfig.routes`'s public, list-of-dicts shape. A real `GET
/health` against the original design returned `400 {"error": "Unknown operation: None"}` — the
marker never arrived. **Fixed with one real agent per route** (`PresidiumGatewayAgent` for
`check_grant`, a new, separate, minimal `HealthCheckAgent` for `/health`) instead of one agent
dispatching on a marker — genuinely simpler, and correctly matches the real, verified API surface.

### The new `GovernedToolProvider.check_grant()` method (presidium core)

```python
class GovernedToolProvider:
    async def check_grant(
        self, agent_name: str, resource: str, action: str = "invoke"
    ) -> PolicyResult:
        """Like check(), but never blocks on approval and never raises.

        `resource` is used exactly as given -- NOT prefixed with "tool:" the
        way check()'s `tool` parameter is (a real naming mismatch found and
        fixed during implementation: an earlier draft shared check()'s own
        "tool:"-prefixing helper, which silently broke FR-1.3's "verbatim"
        requirement -- the shared helper was renamed from `_evaluate_pre_tool`
        to `_evaluate` and now takes a pre-built `resource` string, with
        check() building `f"tool:{tool}"` itself before calling it).

        REQUIRE_APPROVAL decisions are returned as a plain PolicyResult value,
        not resolved synchronously via ApprovalService. Callers with their own
        suspend/resume mechanism (e.g. Civitas's durable suspension, which is
        how civitas-io/fabrica handles this) use this instead of check().
        """
```

Internally, `check()` and `check_grant()` both call a new private `_evaluate(agent_name, resource,
action) -> tuple[PolicyResult, AgentRecord | None]` helper (lookup → `ActionRequest` →
`self._engine.evaluate(...)` → `self._emit_audit(...)`). `check()` keeps its existing
post-evaluation branch (raise on `DENY`, block-and-resolve on `REQUIRE_APPROVAL`); `check_grant()`
returns the raw `PolicyResult` immediately in every case, never raising.

### `PresidiumGatewayAgent` + `HealthCheckAgent` (presidium-contrib, real, shipped)

```python
class PresidiumGatewayAgent(GenServer):
    """Exposes GovernedRuntime.tool_provider.check_grant() over HTTP.

    Built on GenServer (not a plain AgentProcess, which needs self.reply()
    called from inside a live dispatch context) -- the same base class
    PolicyEvaluatorServer/RegistryServer already use, for the same reason: a
    synchronous request/reply agent returning plain dicts is easy to
    unit-test directly (handle_call(payload, "sender")) with no running
    Runtime/Supervisor needed.
    """

    def __init__(self, name: str = DEFAULT_AGENT_NAME, *, runtime: GovernedRuntime, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self._runtime = runtime

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        agent_id = payload.get("agent_id")
        action = payload.get("action")

        if not agent_id or not action:
            return {"decision": "deny",
                    "reason": "Missing required field: 'agent_id' and 'action' are both required",
                    "approval_context": None}

        record = await self._runtime.registry.lookup_by_id(agent_id)
        if record is None:
            return {"decision": "deny", "reason": "Agent not found in registry",
                    "approval_context": None}

        # FR-1.3 ("Option 2, refined"): resource = action verbatim,
        # Presidium's own `action` field is the fixed, generic verb "invoke".
        result = await self._runtime.tool_provider.check_grant(
            record.name, resource=action, action="invoke"
        )

        approval_context = None
        if result.decision == PolicyDecision.REQUIRE_APPROVAL:
            approval_context = {"policy_name": result.policy_name, "reason": result.reason,
                                 "approvers": result.approvers}

        return {"decision": result.decision.value, "reason": result.reason,
                "approval_context": approval_context}


class HealthCheckAgent(GenServer):
    """A real, minimal, always-{"status": "ok"} GenServer for /health."""

    def __init__(self, name: str = DEFAULT_HEALTH_AGENT_NAME, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)

    async def handle_call(self, payload: dict[str, Any], from_: str) -> dict[str, Any]:
        return {"status": "ok"}
```

`scope` (FR-1.4) is designed to thread into `ActionRequest.parameters` via the shared `_evaluate()`
helper's own construction — not yet wired through `PresidiumGatewayAgent.handle_call()`'s real,
shipped code in this first cut (real, honest gap: `_evaluate()`'s current signature takes
`resource`/`action` only, not `parameters`; extending it is a small, real follow-up, not done
speculatively here).

### `GatewayConfig` for the real, minimal, shipped route set

```python
config = build_check_grant_gateway_config(
    port=8443,
    tls_cert="/etc/presidium/server.crt",
    tls_key="/etc/presidium/server.key",
    tls_ca_cert="/etc/presidium/ca.crt",       # a dedicated private CA -- see FR-3.3
    require_mtls=True,                          # the real default
)
# Real, resulting GatewayConfig -- two agents, two routes, no payload_extra
# (see this section's own correction note above for why):
#   routes=[
#       {"method": "POST", "path": "/v1/check_grant", "agent": "presidium.gateway", "mode": "call"},
#       {"method": "GET", "path": "/health", "agent": "presidium.gateway.health", "mode": "call"},
#   ]
```

The caller constructs and registers real `PresidiumGatewayAgent`/`HealthCheckAgent` instances
under the same `Supervisor` as the `HTTPGateway` itself — `build_check_grant_gateway_config()`
only builds the routing config; it does not construct or register the agents (see the function's
own docstring).

### Environment / configuration

| Setting | Source | Notes |
|---|---|---|
| `CIVITAS_GATEWAY_MTLS_ALLOWED_DNS` | env var (Civitas's own) | Semicolon-separated exact-match subject DNs of trusted calling services (e.g. Fabrica's own client cert DN) |
| `tls_ca_cert` | `GatewayConfig` | A dedicated private CA — never a public/broad one (FR-3.3) |
| `key_dir` | `GovernedRuntime` (existing) | Unrelated to mTLS — this is the Ed25519 `AgentRecord.public_key` binding, a different identity layer (FR-3.2) |

---

## Deferred: the fuller REST surface

The original M7 scope named registry CRUD, approval request/list/decide, and credential
resolution as real requirements.

**Registry CRUD — DONE, 2026-08-24, real, shipped.** `presidium_contrib.server.registry_agent`:
`RegisterAgentGatewayAgent` (`POST /v1/agents`), `ListAgentsGatewayAgent` (`GET /v1/agents`),
`GetAgentGatewayAgent` (`GET /v1/agents/{name}`), `DeregisterAgentGatewayAgent`
(`DELETE /v1/agents/{name}`), plus `build_registry_gateway_config()`. **Real, corrected design**:
NOT the `payload["__op__"]` multi-op-per-agent pattern this section originally sketched below —
that exact pattern was already tried and rejected for check_grant/health during M7's own
original implementation (payload_extra is never populated for ordinary, user-declared routes,
confirmed against `civitas.gateway.router.RouteTable.from_config()`). One real GenServer per
real HTTP route instead, matching the corrected, already-verified pattern from the start. New
`presidium_contrib/server/serialization.py` handles real AgentRecord/Grant JSON (de)serialization
(no such helper existed before this).

**A real, previously-unknown, load-bearing framework constraint found while implementing, not
assumed**: `civitas.gateway.dispatch.py`'s own `_call()` classifies ANY reply payload containing
a top-level `"error"` key as `DispatchStatus.AGENT_ERROR`, which maps to a real HTTP 400 --
regardless of whether anything actually raised. Every reply in this module uses `"reason"`
instead, matching `PresidiumGatewayAgent`'s own pre-existing convention (confirmed it already
avoided this pitfall) -- caught this the hard way in a real end-to-end test, not by reading the
framework source first.

**Real, honest scope note**: `GET /v1/agents` does not support the `status`/`trust_tier`/`owner`
query-string filters `AgentRegistry.list_agents()` itself already supports in-process --
`civitas.gateway`'s own dispatch never forwards a route's query string into a `mode: "call"`
route's payload (confirmed directly; only the parsed JSON body and path params are merged). A
real, named, not-yet-built follow-up if filtering becomes concretely needed. Deregister uses
upsert-matching-register semantics: no duplicate-detection/409-Conflict invented beyond what
`AgentRegistry.register()`/`deregister()` themselves already do. Grants are deliberately NOT
settable via the register endpoint (a real, separate, not-yet-built grant-management endpoint
territory) -- confirmed serialized correctly on read when set in-process.

15 new tests (`test_registry_agent.py` unit + `test_registry_gateway_real_http.py` real
end-to-end HTTP), 100% coverage on all three new/changed files, `ruff`/`ruff format --check`/
`mypy --strict` clean.

- **Approval list/decide -- DONE, 2026-08-24, real, shipped, with a real, honest scope
  boundary.** `presidium_contrib.server.approval_agent`: `ListApprovalsGatewayAgent`
  (`GET /v1/approvals`), `ApproveGatewayAgent` (`POST /v1/approvals/{id}/approve`),
  `DenyGatewayAgent` (`POST /v1/approvals/{id}/deny`) -- exposing `ApprovalService.
  list_pending()`/`decide()` directly. **Deliberately does NOT include a `POST /v1/approvals`**
  to originate a request -- approval requests are created in-process by `GovernedToolProvider.
  check()`/`GovernedModelProvider.check()` calling `request_approval()`, never by an external
  network caller (that would let a remote caller inject an arbitrary fake approval). **Real,
  honest, load-bearing scope boundary, confirmed by reading the source, not assumed**:
  `check_grant()` (the one real, existing consumer via `PresidiumGatewayAgent`) does NOT call
  `ApprovalService.request_approval()` at all (confirmed directly in `providers/tool.py`) -- it
  returns `REQUIRE_APPROVAL` as a plain value for the caller's own suspend/resume mechanism
  (FR-1.5), by design. This means an approval surfaced by `check_grant()` over
  `/v1/check_grant` is NOT tracked here and NOT resolvable through these new endpoints -- only
  approvals from the BLOCKING `check()` path are. Wiring `check_grant()`'s own REQUIRE_APPROVAL
  path into a real `ApprovalService` for durable, cross-network resolution is a real, separate,
  bigger integration (it would need to compose with Civitas's own durable suspension mechanism
  on the calling side, e.g. Fabrica) -- explicitly out of scope here, not silently glossed over.
  Also honest about `ApprovalService.decide()`'s own real contract: it has no way to report "no
  such pending request" (confirmed against `CallbackApprovalProvider`'s own implementation, a
  silent no-op for an unknown/already-resolved id) -- these endpoints reply `{"status":
  "decided", ...}` honestly rather than inventing a false-confidence 404 the underlying Protocol
  can't actually back up. Same "one real GenServer per HTTP route" pattern and `"reason"`-not-
  `"error"` reply-key convention as `registry_agent.py`. 13 new tests (unit + real end-to-end
  HTTP), 100% coverage on the new file, `ruff`/`ruff format --check`/`mypy --strict` clean.
- **Credential resolution** would need its own real design pass on what's safe to expose over a
  network at all — deliberately not sketched here to avoid a design that looks more resolved than
  it is.

**Real, pre-existing endpoint sketches worth reusing, not re-deriving**, from the now-superseded
[`http-gateway.md`](archive/http-gateway.md) (a real, older draft that correctly identified "extend
 Civitas's HTTP Gateway" back when it was written, but sat unconnected to any milestone):

```
GET    /v1/agents                    # List registered agents (registry CRUD) -- DONE, 2026-08-24
GET    /v1/agents/{name}             # Get agent details -- DONE, 2026-08-24
GET    /v1/agents/{name}/trust       # Trust score history -- still real, not built
POST   /v1/agents/{name}/suspend     # Suspend an agent -- still real, not built

GET    /v1/policies                  # List policies
POST   /v1/policies/validate         # Validate policy YAML

GET    /v1/approvals                 # Pending approval queue -- DONE, 2026-08-24
POST   /v1/approvals/{id}/approve    # Approve an action -- DONE, 2026-08-24
POST   /v1/approvals/{id}/deny       # Deny an action -- DONE, 2026-08-24
```

The approval endpoints specifically are the real, concrete piece that would let a
`require_approval` decision from `check_grant` actually get resolved over the network — worth
prioritizing first among the deferred set when this milestone's scope expands.

## Implementation status (2026-08-22)

**Real, shipped**: `GovernedToolProvider.check_grant()` (presidium core), `PresidiumGatewayAgent` +
`HealthCheckAgent` + `build_check_grant_gateway_config()` (`presidium_contrib.server`). 39 new
tests across both packages — real Ed25519-free unit tests calling `handle_call()` directly, plus a
real end-to-end suite through an actual `civitas.gateway.HTTPGateway` and real `httpx` requests
over real HTTP (`tests/integration/test_presidium_server_real_gateway.py`). Both new modules at
100% coverage. `ruff`/`mypy --strict` clean.

**Real, honest gap in this first cut**: `scope` (FR-1.4) is not yet threaded through to
`ActionRequest.parameters` — `_evaluate()`'s current signature only takes `resource`/`action`.
CEL policies cannot yet reference `request.parameters` from a `check_grant` call. Small, real,
not-yet-done follow-up, not silently claimed as complete.

**Not yet done, tracked separately, not blocking this milestone's core delivery**: real mTLS
handshake testing (a full private-CA + client-cert integration test) — the current test suite
exercises `require_mtls=False` end to end and `require_mtls=True`'s config assembly in isolation,
not a live handshake. A real, valuable addition, scoped as its own follow-up.

## Open Questions (Deferred)

- Should `PresidiumGatewayAgent` own its `GovernedRuntime` instance, or be constructed with one
  passed in (supporting a deployment where the same `GovernedRuntime` also runs other, in-process
  governed agents)? **Resolved as shipped**: accepts one via a required keyword-only `runtime=`
  parameter, matching `GovernedRuntime`'s own existing dependency-injection style.
- Real load/latency testing against this endpoint is M8's job (Performance Research), explicitly
  sequenced after this milestone ships, not before.
- ~~The `tool` parameter naming mismatch on `check_grant()`~~ — **resolved**: renamed to
  `resource`, and the shared `_evaluate()` helper now takes a pre-built resource string rather than
  auto-prefixing one (see "Real, implemented" above).
- Wiring `scope` (FR-1.4) through to `ActionRequest.parameters` — real, scoped follow-up (see
  "Implementation status" above), not resolved in this cut.
