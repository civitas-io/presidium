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
  identity, not required for this milestone's service-level mTLS.
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

### The new `GovernedToolProvider.check_grant()` method (presidium core)

```python
class GovernedToolProvider:
    async def check_grant(
        self, agent_name: str, tool: str, action: str = "invoke"
    ) -> PolicyResult:
        """Like check(), but never blocks on approval.

        REQUIRE_APPROVAL decisions are returned as a plain PolicyResult value,
        not resolved synchronously via ApprovalService. Callers with their own
        suspend/resume mechanism (e.g. Civitas's durable suspension, which is
        how civitas-io/fabrica handles this) use this instead of check().

        Shares the same registry-lookup + policy-evaluation + audit-emission
        logic as check() via a private helper -- this is not a parallel
        reimplementation, and check()'s own blocking behavior is unchanged.
        """
```

Internally, `check()` and `check_grant()` both call a new private `_evaluate(agent_name, tool,
action) -> PolicyResult` helper (lookup → `ActionRequest` → `self._engine.evaluate(...)` →
`self._emit_audit(...)`). `check()` keeps its existing post-evaluation branch (raise on `DENY`,
block-and-resolve on `REQUIRE_APPROVAL`); `check_grant()` returns the raw `PolicyResult`
immediately in every case.

### `PresidiumGatewayAgent` (presidium-contrib, new)

```python
class PresidiumGatewayAgent(AgentProcess):
    """Thin HTTP-to-GovernedRuntime translation layer. No governance logic of
    its own -- every real decision is GovernedRuntime's.
    """

    def __init__(self, name: str, *, runtime: GovernedRuntime) -> None:
        super().__init__(name)
        self._runtime = runtime

    async def handle(self, message: Message) -> Message | None:
        op = message.payload.get("__op__")
        if op == "check_grant":
            return await self._handle_check_grant(message)
        if op == "health":
            return self.reply({"status": "ok"})
        return self.reply({"error": f"Unknown operation: {op}"})

    async def _handle_check_grant(self, message: Message) -> Message:
        agent_id = message.payload["agent_id"]
        action = message.payload["action"]
        scope = message.payload.get("scope", {})

        record = await self._runtime.registry.lookup_by_id(agent_id)
        if record is None:
            return self.reply(
                {"decision": "deny", "reason": "Agent not found in registry",
                 "approval_context": None}
            )

        # FR-1.3 -- Option 2, refined: resource = action verbatim, action = "invoke" fixed.
        result = await self._runtime.tool_provider.check_grant(
            record.name, action, action="invoke"
        )
        # ActionRequest.parameters carries `scope` for CEL policies that want it (FR-1.4);
        # see the real _evaluate() helper signature for exactly where this is threaded through.

        approval_context = None
        if result.decision == PolicyDecision.REQUIRE_APPROVAL:
            approval_context = {
                "policy_name": result.policy_name,
                "reason": result.reason,
                "approvers": result.approvers,
            }

        return self.reply(
            {
                "decision": result.decision.value,
                "reason": result.reason,
                "approval_context": approval_context,
            }
        )
```

**Real, honest note on the sketch above**: `tool_provider.check_grant(record.name, action,
action="invoke")` calls `GovernedToolProvider.check_grant(agent_name, tool, action)` — the
existing signature's second positional parameter is named `tool` for its original (tool-call)
use case; here it carries the *whole, verbatim* `action` string as the resource identifier per
FR-1.3. This naming mismatch (`tool` parameter, but carrying an arbitrary action string, not a
literal tool name) is worth a real look during implementation — either a doc-comment clarifying
the parameter's real meaning in this call path, or a small, additive alias parameter, decided at
implementation time rather than guessed here.

### `GatewayConfig` for the real, minimal route set

```python
config = GatewayConfig(
    host="0.0.0.0",
    port=8443,
    tls_cert="/etc/presidium/server.crt",
    tls_key="/etc/presidium/server.key",
    tls_ca_cert="/etc/presidium/ca.crt",       # a dedicated private CA -- see FR-3.3
    client_cert_mode="required",
    middleware=["civitas.gateway.mtls.require_client_cert"],
    routes=[
        {
            "method": "POST",
            "path": "/v1/check_grant",
            "agent": "presidium.gateway",
            "mode": "call",
            "payload_extra": {"__op__": "check_grant"},
        },
        {
            "method": "GET",
            "path": "/health",
            "agent": "presidium.gateway",
            "mode": "call",
            "payload_extra": {"__op__": "health"},
        },
    ],
    docs_enabled=False,  # a security product's own API: no public Swagger UI by default
)
```

`payload_extra` is Civitas's own, already-real, already-used mechanism (its auto-registered
topology routes carry `{"__op__": ...}` the identical way) — reused here deliberately, not
invented fresh.

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

## Open Questions (Deferred)

- Should `PresidiumGatewayAgent` own its `GovernedRuntime` instance, or be constructed with one
  passed in (supporting a deployment where the same `GovernedRuntime` also runs other, in-process
  governed agents)? Leaning toward accepting one, matching `GovernedRuntime`'s own existing
  dependency-injection style — not resolved here.
- Real load/latency testing against this endpoint is M8's job (Performance Research), explicitly
  sequenced after this milestone ships, not before.
- The `tool` parameter naming mismatch on `check_grant()` (see the code sketch above) — resolve at
  implementation time.
