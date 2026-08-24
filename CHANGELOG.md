# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.6.0] - 2026-08-24 (presidium-contrib only -- presidium core unchanged)

### Added

#### presidium-contrib -- Approval list/decide over the network

Closes the second of `presidium-server.md`'s "Deferred: the fuller REST surface" items
(registry CRUD shipped first, same day). New `presidium_contrib.server.approval_agent`:
`ListApprovalsGatewayAgent` (`GET /v1/approvals`), `ApproveGatewayAgent`
(`POST /v1/approvals/{id}/approve`), `DenyGatewayAgent` (`POST /v1/approvals/{id}/deny`) --
exposing `ApprovalService.list_pending()`/`decide()` directly.

- Deliberately no `POST /v1/approvals` -- approval requests are created in-process by
  `check()`, never by an external caller.
- **Real, honest scope boundary, confirmed by reading the source**: `check_grant()` does NOT
  call `ApprovalService.request_approval()` at all (by design, per FR-1.5) -- only approvals
  from the blocking `check()` path are tracked and resolvable here. Wiring `check_grant()`'s own
  `REQUIRE_APPROVAL` path into this is a real, separate, bigger integration needing the calling
  side's own durable suspension mechanism (e.g. Fabrica), explicitly out of scope for this pass.
- Honest about `ApprovalService.decide()`'s own real contract (no "not found" signal) -- these
  endpoints reply honestly, not inventing a false-confidence 404.
- 13 new tests, 100% coverage on the new file.

## [0.5.0] - 2026-08-24 (presidium-contrib only -- presidium core unchanged)

### Added

#### presidium-contrib -- Registry CRUD over the network

Closes `presidium-server.md`'s long-standing "Deferred: the fuller REST surface" item. New
`presidium_contrib.server.registry_agent`: `RegisterAgentGatewayAgent` (`POST /v1/agents`),
`ListAgentsGatewayAgent` (`GET /v1/agents`), `GetAgentGatewayAgent` (`GET /v1/agents/{name}`),
`DeregisterAgentGatewayAgent` (`DELETE /v1/agents/{name}`), `build_registry_gateway_config()`.
New `presidium_contrib/server/serialization.py` -- real `AgentRecord`/`Grant` JSON
(de)serialization, built from scratch.

- **Real, corrected design**: one real GenServer per HTTP route, not the `payload["__op__"]`
  multi-op pattern originally sketched for this -- that pattern was already tried and rejected
  for check_grant/health earlier in M7.
- **Real, previously-unknown framework constraint found while implementing**:
  `civitas.gateway.dispatch.py` classifies any reply payload containing a top-level `"error"`
  key as `DispatchStatus.AGENT_ERROR` -> HTTP 400, regardless of whether anything raised. Every
  reply uses `"reason"` instead, matching `PresidiumGatewayAgent`'s own pre-existing convention.
- **Real, honest scope notes**: `GET /v1/agents` doesn't support `list_agents()`'s own
  status/trust_tier/owner filters (civitas's dispatch never forwards query strings into a
  `mode: "call"` route's payload); grants are deliberately not settable via the register
  endpoint; register is upsert, matching `AgentRegistry.register()`'s own real behavior.
- 15 new tests, 100% coverage on all three new/changed files.

## [0.4.0] - 2026-08-24 (presidium-contrib only -- presidium core unchanged)

### Added

#### presidium-contrib -- rate limiting / backpressure at the M7 network boundary

Reuses Civitas's own first-party G4 rate limiter (`civitas.gateway.ratelimit.RateLimiter`/
`rate_limit` middleware -- sliding-window, per-client-IP) rather than building a second
mechanism.

- **`build_check_grant_gateway_config()` gained `rate_limit: bool = False`** -- opt-in, not
  opt-out, unlike `require_mtls`: an availability/operational control with real tuning
  implications (the wrong `max_requests` rejects legitimate traffic), not a fail-closed security
  boundary the way mTLS is.
- **New `build_rate_limiter()`** -- a thin, real constructor wrapper around
  `civitas.gateway.ratelimit.RateLimiter`, exposing `RATE_LIMITER_AGENT_NAME` (`"rate_limiter"`)
  so a caller doesn't need to discover that the middleware's own lookup hardcodes that exact name
  by reading Civitas's source directly.
- Wired onto `/v1/check_grant`'s own per-route middleware specifically, never `/health` or the
  global middleware list -- global and per-route middleware are concatenated per request, not
  deduplicated, so putting mTLS in both would silently run it twice; a liveness probe must never
  be rejected because real traffic used up the check_grant budget.
- Verified end to end: a real running gateway with a real, small budget genuinely returns `429`
  (with `Retry-After`) once exhausted, while `/health` keeps returning `200` throughout. 4 new
  tests, 100% coverage on the changed file.

## [0.3.0] - 2026-08-24

**Real, current numbers**: 469 `presidium` tests (96.16% coverage), 198 `presidium-contrib` tests
(87% coverage, 4 real hardware-gated skips), 3x stable, `ruff`/`ruff format --check`/
`mypy --strict` clean on both packages.

### Changed

#### presidium — `CelPolicyEngine` now fails closed on no policy match (breaking behavioral change)

**Read this before upgrading if you author CEL policies.** Previously, when no policy rule
matched a request for a given stage, `CelPolicyEngine.evaluate()` returned an implicit `ALLOW`
("All policies passed"). It now returns `DENY` (`"No policy rule matched this request
(fail-closed default -- no implicit allow)"`) by default -- the well-established "fail-safe
defaults" principle (Saltzer & Schroeder), matching AWS IAM/Kubernetes RBAC/firewalls, and
consistent with every other `allow_*`-gated fail-closed default already in this codebase.

- **Every policy set now needs an explicit, terminal `ALLOW` rule** if it relies on "nothing
  else objected -> allow" -- this was previously an unwritten, implicit behavior; it must now be
  written down. See the updated `docs/guides/getting-started.md` for a real, working example and
  its own new "Default-deny -- read this before writing your own policies" section.
- **Two explicit, named opt-out knobs** on `CelPolicyEngine.__init__` (and forwarded through
  `presidium_contrib.service.policy.PolicyEvaluatorServer`): `allow_unmatched_requests: bool =
  False` (restores the old always-ALLOW behavior outright) and `unmatched_enforcement:
  EnforcementMode = EnforcementMode.HARD` (run the new DENY decision in `ADVISORY` mode first --
  logged, not blocking -- for a gradual migration).
- Full reasoning: `docs/design/policy-engine.md`'s corrected P5 decision.

### Added

#### presidium + presidium-contrib -- `AgentGatewayClient`: real MCP tool-side and A2A delegation

Real vendor research first (`docs/design/agentgateway-vendor-research-2026-08.md`,
`docs/design/a2a-delegation-vendor-research-2026-08.md`), then implementation:

- **New `presidium.providers.gateway` module**: `LLMGatewayBackend`/`ToolsGatewayBackend`
  Protocols, `GatewayModelProvider`/`GatewayToolProvider` -- a third composition pattern
  (wraps a real, separate, network-reachable gateway process) alongside pure-authorization
  `GovernedModelProvider`/`GovernedToolProvider` and `civitas_adapters.py`'s direct in-process
  Civitas provider wrapping.
- `GovernedToolProvider` gained `check_resource()`/`post_check_resource()` (verbatim-resource
  variants of `check()`/`post_check()`, needed for the new `agent:<name>` grant namespace
  alongside `tool:<name>`).
- **`AgentGatewayClient.list_tools()`/`call_tool()`** -- real MCP `tools/list`/`tools/call` over
  Streamable HTTP, the exact transport `civitas-io/python-civitas` GH #26 shipped. Verified end
  to end against a real running MCP server, not mocked.
- **`AgentGatewayClient.delegate_to_agent()`** -- real A2A delegation using the official `a2a-sdk`
  (new dependency, `>=1.1.2`, on the `[agentgateway]` extra). `AgentGatewayClient` gained
  `a2a_routes: dict[str, str] | None` (an explicit target-agent-name -> gateway-route-URL map,
  since AgentGateway's A2A proxy routes per-upstream-agent, unlike MCP's single federated
  endpoint). Maps `arguments["text"]` onto a real A2A text message or the whole dict onto a
  structured data message. New `AgentGatewayDelegationError`. Verified end to end against a real
  running A2A server (a faithful port of the official `a2a-samples` Hello World reference agent).
- Any `AgentGateway` pin must be `>=1.4.0` -- `GHSA-mvgg-jvj2-4frq` (HIGH severity, session/authz
  confusion across routes) is fixed exactly there.

#### presidium-contrib -- `[spiffe]`: real SPIRE-issued X.509-SVID identity

- **New `presidium_contrib.spiffe` module** (`SpiffeIdentitySource`, `bind_identity_to_registry()`
  -- new `[spiffe]` extra, `spiffe>=0.3.1`): a real async bridge over the official `spiffe` SDK's
  Workload API client (a blocking, thread-based API, bridged correctly via `asyncio.to_thread()`/
  `asyncio.run_coroutine_threadsafe()`).
- **`AgentRecord` gained `public_key_algorithm: Literal["ed25519", "ec_p256"] = "ed25519"`** --
  additive, default unchanged for every existing caller. `presidium.identity.verify_agent_signature()`
  dispatches on it; the Ed25519 path is completely untouched. `cryptography>=41` is now a real,
  hard core `presidium` dependency (same lazy-import-but-hard-dependency precedent as `pynacl`).
- **New `AgentRegistry.update_identity(name, public_key, public_key_algorithm)`** across all
  three backends -- real identity rotation support.
- Verified end to end against an actual running SPIRE v1.15.3 server + agent on real hardware,
  confirming a genuine EC P-256 X.509-SVID with the SPIFFE ID as its SAN URI.

#### presidium-contrib -- `GovernedMcpToolPipeline`: composes the three MCP governance primitives

**New `presidium_contrib.mcp_gateway.pipeline.GovernedMcpToolPipeline`.** `PIIDetector`/
`PoisoningDetector`/`redact_dict` were real, tested, shipped primitives with zero real
composition until now. The new pipeline runs, per tool call: a poisoning check (fail-closed by
default, `allow_unapproved_tools` opt-out) -> `redact_dict()` of arguments into
`ActionRequest.parameters` for policy/audit visibility -> real `PRE_TOOL` authorization -> the
real, unredacted backend call -> optional `PIIDetector.scan_dict()` enrichment of the result with
`contains_pii`/`pii_pattern_names` (opt-in by `pii_detector` presence) -> real `POST_TOOL`
authorization (a CEL policy can now genuinely reference `result.contains_pii`) -> optional
`PIIDetector.mask_dict()` of the value actually returned to the agent (`mask_pii_in_results`, on
by default).

#### presidium -- `scope` (FR-1.4) threaded through `check_grant()`/`check()`/`check_resource()`

`GovernedToolProvider.check_grant()`/`check()`/`check_resource()` gained an additive, optional
`parameters: dict[str, Any] | None = None`. `presidium_contrib.server`'s `PresidiumGatewayAgent`
now actually reads the HTTP request body's `scope` field and passes it through -- previously
silently discarded despite being part of the documented request shape from the start. A CEL
policy can now genuinely reference `request.parameters.<key>` from a `check_grant` call.

#### presidium -- Trust ceiling propagation and monotonic capability narrowing

Two real, concrete security gaps found via a direct comparison against Microsoft's Agent
Governance Toolkit (`microsoft/agent-governance-toolkit`), now closed:

- **Trust ceiling propagation** — closes a real "trust washing" gap where an agent (or a
  compromised orchestrator) could repeatedly spawn fresh children to reset a degraded trust score.
  New `AgentRecord.trust_ceiling: float | None`; `LinearTrustScore` gained an optional `ceiling`
  param clamping its `.value` getter (a hard boundary respected even by `HUMAN_OVERRIDE`/
  `set_value()` — an admin who wants to grant more trust must explicitly raise `trust_ceiling`
  itself, not smuggle it through an override). New `presidium.lineage.compute_child_ceiling()`.
- **Monotonic capability narrowing on delegation/spawn** — closes a real, open security hole
  where a spawned/delegated child could end up with *more* grants than its parent. New
  `presidium.lineage.validate_grant_narrowing()` (subset-of-parent check on (resource, action)
  pairs) and `presidium.lineage.compute_child_depth()` (a configurable, AGT-matching
  `max_delegation_depth`, default 10). New `AgentRecord.depth`.
- Both enforced inside `register()`/`add_grant()` on **all three registry backends**
  (`InMemoryRegistry`, `SqliteRegistry`, `PostgresAgentRegistry`) — defense in depth at the
  registry API itself, not an opt-in helper a caller could bypass. A dangling `parent_agent_id`
  now fails closed with a new `UnresolvableParentError` rather than being silently ignored.
- New errors: `UnresolvableParentError`, `GrantEscalationError`, `DelegationDepthExceededError`
  (all `RegistryError` subclasses).
- **Behavioral note for existing integrations**: registering or granting to an agent with
  `parent_agent_id` set now performs real validation that didn't exist before — previously it was
  pure, unvalidated metadata. No real caller in this codebase or its dependents currently
  constructs a live spawn-and-register composition (confirmed: Civitas's `Runtime.spawn()` has no
  Presidium awareness; Fabrica's `CivitasBridge.request_supervision()` is a pass-through, not
  called by Fabrica's own managers in v1), so the practical blast radius today is zero — this
  closes the hole before a real orchestrator is built on top of it, not after.
- 60+ new tests (pure-function tests, registry-level integration tests across all three
  backends). All 439 `presidium` + 158 `presidium-contrib` tests pass, 3x stable,
  `ruff`/`mypy --strict` clean.

### Fixed

#### presidium-contrib -- real mTLS handshake test now passes for real, not `xfail`

`civitas>=0.11.3` (`civitas-io/python-civitas` GH #25 R10) fixed a real, upstream gap where
`mtls_source="direct"` HTTP mTLS never actually exposed the client certificate to the ASGI app.
The two previously-`xfail(strict=True)`-marked scenarios in `presidium-contrib`'s own real mTLS
handshake test now pass for real against the published dependency -- markers removed, not
loosened.

### Developer Experience

- **Real, working pre-commit hooks -- installed and verified, not just configured.** A
  `.pre-commit-config.yaml` existed since June but was never actually installed
  (`.git/hooks/pre-commit` didn't exist). Now real: ruff/ruff-format/gitleaks on every commit,
  `mypy --strict` + the full test suite on every push. `pre-commit>=3.7` added as a dev
  dependency; `CONTRIBUTING.md` corrected (it had drifted to describe the project as
  pre-implementation despite substantial real, published, tested code).
- `AGENTS.md` corrected -- no longer claims `litellm`/`kong`/`portkey`/`cloudflare_ai_gateway`/
  `helicone`/`truefoundry` extras/modules exist (they don't); fixed stale module names
  (`presidium.protocols`/`presidium.models` -> the real, distributed Protocols + singular
  `presidium.model`), a stale "Pre-alpha" status line, and a monorepo tree missing
  `presidium.identity`/`presidium.lineage`/`presidium_contrib.spiffe`/`presidium_contrib.server`.

## [0.2.1] - 2026-08-22

### Fixed

#### presidium — A real, live packaging bug: `import presidium` failed without the `[sqlite]` extra

- **`presidium/__init__.py` eagerly imports `SqliteRegistry`, and `presidium.registry.sqlite`
  unconditionally `import`ed `aiosqlite` at module level** — meaning a plain `pip install
  presidium` (the documented, base install) could not even `import presidium` at all. **Found by
  actually verifying the real, just-published v0.2.0 wheel in a fresh venv, not assumed working**
  — the exact verification step this project's own discipline calls for, which is precisely what
  caught this before it went any further unnoticed.
- Fixed with the same lazy-import + helpful-error pattern `civitas.security.identity` already
  uses for `pynacl` (`"pip install 'civitas[security]'"`): `aiosqlite` is now only imported inside
  `SqliteRegistry._conn()`, on first real use, raising a real, helpful `PresidiumError` ("Install
  it with: pip install 'presidium[sqlite]'") if genuinely missing. Constructing a `SqliteRegistry`
  instance no longer requires `aiosqlite` at all — only actually using it does.
- **`presidium-contrib` does not have this bug** — its own `__init__.py` is empty and eagerly
  imports nothing, confirmed by the same real, fresh-venv verification. No fix needed there.
- 3 new tests, including a cheap, precise, direct regression guard (source-inspects
  `presidium/registry/sqlite.py` for a reintroduced module-level `import aiosqlite`) so this exact
  class of bug can't silently recur. All 380 tests pass, 3x stable.

## [0.2.0] - 2026-08-22

**First real, published release** (`presidium`/`presidium-contrib` were never previously tagged
or published to PyPI — confirmed live via PyPI's own JSON API returning 404 for both, and no git
tags existed before this release). Versioned `0.2.0`, not `0.1.0`, specifically to avoid colliding
with this file's own pre-existing `[0.1.0] - 2026-06-14` entry below, which documents a real, but
never-published, M2-completion snapshot — everything in this `[0.2.0]` entry represents real,
substantial, additional work since then (M3 complete, M7/
Presidium Server shipped end to end, drop-in Civitas provider adapters, a real Ed25519 identity
fix). `Development Status` classifier bumped `2 - Pre-Alpha` → `3 - Alpha` to match, per
`civitas-io/fabrica`'s own precedent at a comparable stage of real, tested maturity.

**Real, current numbers**: 377 presidium core tests (95.69% coverage), 153 presidium-contrib
tests (83% coverage), 3x stable, `ruff`/`mypy --strict` clean on both packages.

### Added

#### presidium — Drop-in Civitas ModelProvider/ToolProvider adapters (2026-08-22)

- **New `presidium.providers.civitas_adapters` module**: `GovernedModelProviderAdapter`/
  `GovernedToolAdapter`, real structural implementations of
  `civitas.plugins.model.ModelProvider`/`civitas.plugins.tools.ToolProvider`. Each wraps one real
  backend + policy enforcement, constructed **per agent** (`agent_name` bound at construction) —
  the same, already-established pattern `civitas.process.AgentProcess.connect_mcp()` uses for
  `civitas-io/fabrica`'s own `MCPTool`.
- **`GovernedRuntime` gained `model_for(agent_name, backend)`/`tool_for(agent_name, backend)`**
  factory methods, mirroring Civitas's own `AgentProcess.model_for()` naming convention. A
  governed agent's own `on_start()` sets `self.llm = governed_runtime.model_for(self.name,
  backend=real_provider)` to make its LLM/tool calls governed, transparently.
- `PolicyDeniedError` still **raises** on DENY here (reusing `check()`'s existing behavior
  exactly) — a real, deliberate difference from `presidium_contrib.server`'s non-raising
  `check_grant()` HTTP boundary; an in-process exception through the calling agent's own error
  boundary is the correct, idiomatic Civitas convention for this use case.
- 13 new tests, both new/touched modules at 100%/83% coverage.

#### presidium + presidium-contrib — Presidium Server: check_grant() shipped (2026-08-22)

- **`GovernedToolProvider.check_grant(agent_name, resource, action="invoke") -> PolicyResult`** —
  a real, new, additive method in `presidium` core. Like `check()`, but never blocks on
  `REQUIRE_APPROVAL` (returns it as a plain value) and never raises (an unresolvable
  `agent_name` returns a `DENY` `PolicyResult`, not an exception). Shares lookup/evaluate/audit
  logic with `check()` via a renamed, generalized private helper (`_evaluate_pre_tool` →
  `_evaluate`, now takes a pre-built `resource` string instead of a `tool` name it silently
  prefixed with `"tool:"`).
- **New `presidium_contrib.server` module** (`presidium-contrib[server]` extra, needs
  `civitas[http]` + `cryptography`): `PresidiumGatewayAgent` (exposes `check_grant()` over HTTP),
  `HealthCheckAgent`, `build_check_grant_gateway_config()`. Satisfies `civitas-io/fabrica`'s
  `PresidiumClient.check_grant()` contract exactly over real REST.
- 39 new tests across both packages (real unit tests calling `handle_call()` directly, plus a
  real end-to-end suite through an actual `civitas.gateway.HTTPGateway` and real `httpx` requests
  over real HTTP). Both new modules at 100% coverage.

#### presidium — Real Ed25519 identity binding (2026-08-22)

- **`GovernedRuntime` now binds a real, persistent Ed25519 identity per agent** via
  `civitas.security.identity.AgentIdentity.load_or_generate()` — previously hardcoded
  `AgentRecord(public_key="", ...)` despite this being documented as delivered M2 behavior.
  New `key_dir` constructor param (default `.presidium/keys`), configurable via
  `presidium.registry.key_dir` in topology YAML.
- **New `presidium.identity` module** with `verify_agent_signature()`, the shared, pure-function
  verification primitive every `AgentRegistry` backend delegates to. Fails closed as a plain
  `False` return (never raises) for every failure case: unknown agent, unbound/empty public key,
  malformed public key, missing `pynacl`, or a genuinely invalid signature.
- **`AgentRegistry` Protocol gained `verify_signature(name, data, signature) -> bool`**,
  implemented in `InMemoryRegistry`, `SqliteRegistry`, and `presidium-contrib`'s
  `PostgresAgentRegistry`.
- `pynacl>=1.5` is now a direct, required dependency of `presidium` (identity binding is a core,
  always-on capability, not opt-in).
- 18 new tests (real Ed25519 keypairs and real sign/verify round trips, not mocked crypto).
  Coverage: presidium core 90.97% → 95.24%.

#### presidium — Dependency and type-checking cleanup (2026-08-22)

- **`civitas` dependency bumped `>=0.3` → `>=0.11.0`, resolved from real PyPI** — removed the
  workspace root's `[tool.uv.sources]` git override (`branch = "main"`), matching
  `civitas-io/fabrica`'s own precedent. `civitas>=0.11.0` has been real and published on PyPI for
  some time; there was no remaining reason to float on an unpinned branch.

#### presidium-contrib — Service Mode test coverage: 0% → 100%, a second real bug found (2026-08-22)

- **`presidium_contrib.service.policy`/`.registry` now have real test coverage (0% → 100%)** —
  14 new tests: direct `handle_call()` unit tests plus a real end-to-end suite through an actual
  `civitas.Runtime`/`Supervisor` (`tests/integration/test_service_mode_real_runtime.py`),
  including a dedicated regression test for the `RegistryServer` attribute-collision fix below.
- **Fixed:** `PolicyEvaluatorServer._handle_load()` stored a raw string in `PolicyRule.decision`
  instead of converting it to the `PolicyDecision` enum. `CelPolicyEngine.evaluate()` accepted it
  silently, but `_handle_evaluate()`'s own `result.decision.value` then crashed with a real
  `AttributeError` on every non-default-ALLOW decision. 0% test coverage had masked this entirely;
  caught immediately by the first real test exercising a non-trivial policy outcome. Matches
  `GovernedRuntime._parse_policy_rules()`'s own correct pattern.

#### presidium-contrib — Real attribute-name collision in `RegistryServer` (2026-08-22)

- **Fixed:** `RegistryServer` named its own governance registry `self._registry`, colliding with
  `civitas.process.AgentProcess`'s own reserved `_registry` attribute (Civitas's internal
  name-routing registry, used by `suspend()`/`resume()`/capability-based routing/spawn-target
  resolution). A real `Supervisor` wiring a `RegistryServer` into a live tree
  (`agent._registry = self._registry` in `civitas/supervisor.py`) would silently clobber one with
  the other. Renamed to `self._agent_registry`. Found only after the `civitas` PyPI-pin fix above
  made `civitas`'s own real `py.typed` marker visible for the first time, which surfaced this bug
  through a previously-unused, overly-broad `# type: ignore[misc]` comment that had been
  suppressing real type errors in the class body, not just the class definition line. The same
  now-unused ignore comment was also removed from `GovernedMessageBus` and
  `PolicyEvaluatorServer` (both clean without it).
- Added missing `mypy` override entries for `hvac`/`asyncpg` (no published type stubs for
  either) — found adjacent to the above while re-running a clean `mypy` pass.

#### presidium — Remaining M3 Core Features

- **PRE_MESSAGE evaluation stage**: `EvaluationStage.PRE_MESSAGE` for inter-agent message governance via Civitas MessageBus hook
- **Policy hot-reload**: `GovernedRuntime.reload_policies(path)` atomically replaces compiled rules from YAML without restart; `CelPolicyEngine.load_policies()` now uses atomic swap instead of clear-then-populate
- 336 core tests passing, 97% coverage

#### presidium-contrib — MCP Governance + Service Mode

- **Tool poisoning detection**: `PoisoningDetector` with hash-based `ToolSnapshot` fingerprinting; detects description/parameter changes after approval
- **Credential redaction**: `redact_string()` / `redact_dict()` with regex patterns for API keys, Bearer tokens, AWS keys, GitHub PATs; recursive nested dict support
- **PII detection**: `PIIDetector` with configurable regex patterns (SSN, credit card, email, phone, IP); `scan_string()`, `scan_dict()`, `mask_string()`, `mask_dict()` methods
- **Service mode GenServer wrappers**: `PolicyEvaluatorServer` and `RegistryServer` expose governance components as Civitas GenServer processes for distributed deployments

#### presidium — Enterprise Trust Requirements (M3: FR-E.1–E.6)

- **FR-E.1 Spec Pinning**: `WindowedTrustScorer(pinned_spec_hash=...)` validates scorer config hash at construction; raises `SpecMismatchError` on mismatch
- **FR-E.2 Override Attribution**: `HUMAN_OVERRIDE` events require `actor_id` in `EventContext`; raises `MissingAttributionError` when missing
- **FR-E.3 Performance Budget**: Benchmark tests verify <1ms p99 for `.value` and `.tier` reads with 100 events
- **FR-E.4 Zero-Downtime Migration**: M2 `TrustEvent` enum values flow into M3 `WindowedTrustScorer` without re-scoring
- **FR-E.5 Determinism Contract**: `deterministic: bool` class attribute on scorers (`LinearTrustScore`=True, `WindowedTrustScorer`=True, `LearningTrustScorer`=False); added to `IntrospectableScorer` Protocol
- **FR-E.6 OpenTelemetry**: `presidium.trust.telemetry` module with no-op fallback; spans on `record_event` and `value` reads with `trust.agent_id`, `trust.event_type`, `trust.value`, `trust.tier`, `trust.spec_hash` attributes; `presidium[otel]` optional extra
- New errors: `TrustScoringError`, `SpecMismatchError`, `MissingAttributionError`
- `WindowedTrustScorer` gains `agent_id` parameter for OTel span attribution

#### presidium-contrib — LearningTrustScorer Refactor

- Refactored `LearningTrustScorer` to delegate scoring math to `presidium.scoring.functions`
- Implements `IntrospectableScorer` (`.spec`, `.deterministic`) and `QueryableScorer` (`.recent_events()`) Protocols
- Enforces override attribution (FR-E.2) on `HUMAN_OVERRIDE` events
- Added `LearningAudit` dataclass and `learning_audits` property for FR-3.6/FR-3.7 bounded learning
- Accepts `DecayConfig`, `WindowConfig`, `ColdStartStrategy`, injectable clock
- `max_weight_delta` parameter caps per-invocation weight changes (FR-3.7, default 0.05)

## [0.1.0] - 2026-06-14

### Added

#### presidium 0.1.0 — Core Governance Library

**Data Model (Phase 1)**
- 8 enums: `AgentStatus`, `TrustTier`, `TrustEvent`, `PolicyDecision`, `EvaluationStage`, `EnforcementMode`, `ApprovalStatus`
- 8 dataclasses: `Grant`, `AgentRecord`, `PolicyRule`, `PolicyResult`, `ActionRequest`, `EvaluationContext`, `ApprovalRequest`, `ApprovalDecision`
- `PresidiumError` hierarchy with 9 domain-specific exception classes
- SPIFFE-compatible `presidium://` agent identity URIs

**Trust Scoring (Phase 2)**
- `TrustScorer` Protocol with `value`, `tier`, `last_updated`, `record_event`
- `LinearTrustScore` — lazy-on-read decay (-0.01/hr), materialize-on-write, 3 tiers (TRUSTED ≥ 0.7, STANDARD ≥ 0.3, RESTRICTED < 0.3)

**Policy Engine (Phase 2-3)**
- `PolicyEngine` Protocol with `load_policies()` and `evaluate()`
- `CelPolicyEngine` — CEL-based evaluation via cel-python, compile-once, first-match-wins by priority, fail-closed on errors
- 5 evaluation stages: `PRE_TOOL`, `PRE_LLM`, `REGISTRATION`, `POST_TOOL`, `POST_LLM`
- 3 enforcement modes: advisory (log only), soft (warn), hard (block)
- Grant pre-filtering: expired and condition-false grants excluded before evaluation

**Credential Provider (Phase 2)**
- `CredentialProvider` Protocol with grant-based access control
- `EnvCredentialProvider` — os.environ lookup with `credential:{name}` grant checking
- `FileCredentialProvider` — key=value file parsing with grant checking

**Agent Registry (Phase 3, 6)**
- `AgentRegistry` Protocol with 12 async methods (CRUD, grants, trust, status)
- `InMemoryRegistry` — dict-backed with deep-copy snapshot semantics, revision counter, trust delegation to `LinearTrustScore`
- `SqliteRegistry` — async SQLite via aiosqlite, WAL mode, asyncio.Lock write serialization, parametrized test parity with InMemoryRegistry

**Approval Service (Phase 3)**
- `ApprovalService` Protocol with `request_approval`, `list_pending`, `decide`
- `CallbackApprovalProvider` — auto-approve, auto-deny, callback function, and manual mode (asyncio.Future + timeout), fail-closed on timeout

**Audit Enricher (Phase 4)**
- `AuditEnricher` Protocol (structural subtype of AuditSink)
- `InProcessAuditEnricher` — middleware wrapping downstream sink, adds `details.governance` context, TTL cache, re-enrichment guard, fail-open on errors

**Governed Providers (Phase 5)**
- `GovernedModelProvider` — PRE_LLM + POST_LLM policy enforcement, ALLOW/DENY/REQUIRE_APPROVAL, advisory/soft/hard modes, audit event emission
- `GovernedToolProvider` — PRE_TOOL + POST_TOOL policy enforcement, same three-decision flow

**GovernedRuntime (Phase 6)**
- `GovernedRuntime` — programmatic constructor wiring all governance components
- `GovernedRuntime.from_config()` — YAML-based construction, extracts `presidium:` block, delegates to `Runtime.from_config_dict()`

#### presidium-contrib 0.1.0 — Adapters

- Package scaffold with 8 adapter/reference-impl stub modules
- `WebhookApprovalProvider` — POST approval requests to webhook URL, wait for callback, fail-closed on timeout/delivery failure
- `OPAPolicyEngine` — wraps OPA REST API (/v1/data/), maps evaluation stages to OPA package paths, fail-closed on connection errors

#### Infrastructure

- GitHub Actions CI: test both packages on Python 3.12/3.13, ruff lint+format, mypy strict
- Pre-commit hooks: trailing whitespace, EOF fixer, YAML/TOML checks, ruff, gitleaks
- Makefile: install, lint, format, test, typecheck, check, clean
- EditorConfig for consistent formatting
- 271 tests total (256 presidium + 15 presidium-contrib), 95%+ coverage
