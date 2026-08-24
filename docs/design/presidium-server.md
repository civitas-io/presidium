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

- Registry CRUD, approval request/list/decide, credential resolution over the network — designed
  conceptually (see "Deferred: the fuller REST surface" below), not built.
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
resolution as real requirements. All remain real, designed intents — not built in this cut because
nothing concretely calls them over a network yet. When a real consumer appears:

- **Registry CRUD** would follow the same `PresidiumGatewayAgent` pattern — new `__op__` values
  (`register`, `deregister`, `lookup`, `list`), delegating to `self._runtime.registry` directly
  (no new orchestration needed, since registry operations don't compose with policy/approval the
  way `check_grant` does).
- **Approval request/list/decide** is the real piece that would let a `REQUIRE_APPROVAL` decision
  from `check_grant` actually get resolved over the network — genuinely useful work, deferred
  because `check_grant` returning the decision as a value (FR-1.5) is useful on its own even
  before a network-reachable resolution path exists (a caller can still route it through its own,
  local human-approval mechanism in the meantime).
- **Credential resolution** would need its own real design pass on what's safe to expose over a
  network at all — deliberately not sketched here to avoid a design that looks more resolved than
  it is.

**Real, pre-existing endpoint sketches worth reusing, not re-deriving**, from the now-superseded
[`http-gateway.md`](http-gateway.md) (a real, older draft that correctly identified "extend
 Civitas's HTTP Gateway" back when it was written, but sat unconnected to any milestone):

```
GET    /v1/agents                    # List registered agents (registry CRUD)
GET    /v1/agents/{name}             # Get agent details
GET    /v1/agents/{name}/trust       # Trust score history
POST   /v1/agents/{name}/suspend     # Suspend an agent

GET    /v1/policies                  # List policies
POST   /v1/policies/validate         # Validate policy YAML

GET    /v1/approvals                 # Pending approval queue
POST   /v1/approvals/{id}/approve    # Approve an action
POST   /v1/approvals/{id}/deny       # Deny an action
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
