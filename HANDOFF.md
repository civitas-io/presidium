# Handoff: Presidium

**Purpose of this doc:** resume work cold, after a context compaction, without re-deriving
anything already decided. Read this first, then follow the links — don't re-read the whole repo
linearly. Deep, dated engineering history (every finding, every real decision, why) lives in
[`docs/log.md`](docs/log.md); the ordered work queue lives in
[`docs/vision/roadmap.md`](docs/vision/roadmap.md)'s own "Implementation Priority" section.

**Cross-project context**: this project is one of three real pillars in the `civitas-io` org
(Civitas = runtime, Presidium = this repo, governance, Fabrica = context layer). The private
`civitas-io/context` repo is the cross-repo reasoning substrate -- `projects/presidium.md` there
mirrors everything below in more narrative form, kept in sync after every real change.

## Status as of 2026-08-24: **presidium v0.3.0 and presidium-contrib v0.3.0 are real, live on PyPI**

```
pip install presidium          # 0.3.0
pip install presidium-contrib  # 0.6.0
pip install "presidium-contrib[agentgateway,spiffe,server]"  # real MCP+A2A gateway client, real SPIRE identity, M7 server + rate limiting + registry CRUD + approval list/decide
```

Confirmed via a real fresh-venv install against the actual published PyPI packages (not local
source) -- base imports, the new `providers.gateway`/`identity`/`lineage` modules,
`[agentgateway]`/`[spiffe]` extras, and `presidium_contrib.server`'s `build_rate_limiter()`/
`rate_limit=` toggle, registry CRUD gateway agents, and approval list/decide gateway agents.
GitHub Releases: [`v0.3.0`](https://github.com/civitas-io/presidium/releases/tag/v0.3.0),
[`contrib-v0.3.0`](https://github.com/civitas-io/presidium/releases/tag/contrib-v0.3.0),
[`contrib-v0.4.0`](https://github.com/civitas-io/presidium/releases/tag/contrib-v0.4.0) (rate
limiting), [`contrib-v0.5.0`](https://github.com/civitas-io/presidium/releases/tag/contrib-v0.5.0)
(registry CRUD), [`contrib-v0.6.0`](https://github.com/civitas-io/presidium/releases/tag/contrib-v0.6.0)
(approval list/decide) -- `presidium` core stayed at `v0.3.0` throughout, no changes needed for
any `presidium-contrib`-only release. All with real CycloneDX SBOM assets. `presidium`
tagged/published first (confirmed live via PyPI's JSON API) before `presidium-contrib` -- its
own dependency floor is now `presidium>=0.3.0`, a real fix caught before release (it was still
`>=0.1`, which would have let a fresh `presidium-contrib` install silently resolve an
incompatible `presidium` missing `providers.gateway`). **Real, expected PyPI propagation delay
hit three times across these verifications** (a bare/pinned `pip install presidium-contrib`
briefly still resolved the previous version right after each publish) -- matches this org's own
documented "wait and re-check via the JSON API" precedent, not a real release bug.

**Everything in this file below the CHANGELOG-summarized entries is now genuinely live and
installable**, not just committed to `main` -- see `CHANGELOG.md`'s `[0.3.0]` entry for the
single, comprehensive summary of what shipped since v0.2.1/v0.2.0.

**GH #26 (Streamable HTTP MCP transport, python-civitas/fabrica) -- DONE, closed, benchmarked.**
See either of those repos' own `HANDOFF.md` for the real detail.

**`AgentGatewayClient`'s MCP tool-side gap -- DONE, 2026-08-24.** Vendor research
([`docs/design/agentgateway-vendor-research-2026-08.md`](docs/design/agentgateway-vendor-research-2026-08.md))
fed directly into a real design pass (`docs/design/mcp-gateway.md`'s "Design decisions,
2026-08-24") and real implementation, same session:

- **New `presidium/providers/gateway.py`**: `LLMGatewayBackend`/`ToolsGatewayBackend` Protocols
  (previously design-doc-only), `GatewayModelProvider`/`GatewayToolProvider` -- a real, third
  composition pattern alongside `GovernedModelProvider`/`GovernedToolProvider` (pure
  authorization) and `civitas_adapters.py`'s `GovernedModelProviderAdapter`/`GovernedToolAdapter`
  (direct in-process Civitas provider wrapping). 13 new tests, 100% coverage on the new file.
- **`GovernedToolProvider` gained `check_resource()`/`post_check_resource()`** -- verbatim-
  resource variants of `check()`/`post_check()` (which always auto-prefix `tool:`), needed for
  the new `agent:<name>` grant namespace. `check()`/`post_check()` are now thin wrappers over
  these -- a real, safe refactor, all 439 pre-existing tests confirmed still passing unchanged.
  **A real double-prefix bug (`"tool:agent:<name>"`) was caught and fixed during implementation,
  before it shipped**, not after -- exactly the kind of thing this org's own "verify, don't
  assume" discipline exists to catch.
- **`AgentGatewayClient.list_tools()`/`call_tool()` -- real MCP `tools/list`/`tools/call` over
  Streamable HTTP**, using the exact `mcp.client.streamable_http.streamable_http_client` GH #26
  shipped. Verified end to end against a real running MCP server (not mocked) --
  `tests/integration/test_agentgateway_mcp_real_server.py`, 5 tests. New `mcp>=2.0` dependency on
  the `[agentgateway]` extra; confirmed via a real editable install that the base
  `presidium-contrib` package (no extra) still imports fine, and `agentgateway.client` fails
  cleanly (pre-existing behavior, not a new gap) without the extra installed.
- **`AgentGatewayClient.delegate_to_agent()` deliberately raises `NotImplementedError`**, not a
  silent stub -- the A2A half needs a real `a2a-sdk` dependency and its own real test, named as
  an explicit, separate follow-up (design decision 3), not attempted in this pass.
- **Decision made, not left open**: AgentGateway's own native MCP authorization is left
  configured permissively for this integration in v1 -- Presidium is the sole authorization
  authority for this path. Real, named revisit trigger recorded if that assumption changes.

167 presidium-contrib tests pass (was 162, +5 real new ones), 452 presidium tests pass (was 439,
+13 new), `ruff`/`mypy --strict` clean on both packages' `src/`.

**`presidium-contrib[spiffe]` -- DONE, 2026-08-24.** Real vendor research
([`docs/design/spiffe-vendor-research-2026-08.md`](docs/design/spiffe-vendor-research-2026-08.md))
into a real design pass and implementation, verified end to end against an actual running SPIRE
v1.15.3 server + agent on the homelab -- not mocked:

- **`AgentRecord` gained `public_key_algorithm`** (`"ed25519"` default, `"ec_p256"` additive) --
  `presidium.identity.verify_agent_signature()` now dispatches on it; the Ed25519 path is
  completely untouched. `cryptography>=41` added as a real, hard core `presidium` dependency,
  matching `pynacl`'s own exact precedent (lazily imported for graceful degradation, but a real
  declared dependency, not a new optional extra).
- **New `AgentRegistry.update_identity()`** across all three backends (`InMemoryRegistry`,
  `SqliteRegistry`, `PostgresAgentRegistry`) -- real rotation support, since nothing before this
  could ever update an existing agent's stored identity at all.
- **Two real bugs caught and fixed DURING implementation, before they shipped**: `SqliteRegistry`
  and `PostgresAgentRegistry`'s shared `_save()` helper never included `public_key`/
  `public_key_algorithm` in its `UPDATE` statement at all -- harmless before now (the key was
  immutable), but would have made `update_identity()` silently no-op on both backends.
- **New `presidium_contrib.spiffe`** (`SpiffeIdentitySource`, `bind_identity_to_registry()`) --
  a real async bridge over the official `spiffe` SDK's Workload API client, which is itself a
  **blocking, thread-based API, confirmed directly against its own source, not asyncio-native**
  (unlike everything else in this org's codebase). The blocking constructor runs via
  `asyncio.to_thread()`; the SDK's own synchronous rotation callback is bridged back via
  `asyncio.run_coroutine_threadsafe()`.
- **Verified for real on the homelab**: a real SPIRE v1.15.3 server + agent, a real registration
  entry, a real fetched X.509-SVID confirmed as genuine EC P-256 with the SPIFFE ID as its SAN
  URI -- exactly as predicted by the vendor research, not assumed. 5 real end-to-end tests pass
  there (correctly hardware-gated-skipped elsewhere, matching Fabrica's own `srt`-availability
  precedent), plus 4 new pure-function tests (no server needed) for the key-extraction logic.
- **Explicitly NOT built, named not hidden**: certificate-based mTLS between agents and
  cross-deployment federation via trust domain bundles -- real, separate future directions.

462 `presidium` tests pass (+10), 174 `presidium-contrib` tests pass (+5, all real on the
homelab), `ruff`/`mypy --strict` clean on both packages' `src/`.

---

## Status as of 2026-08-22: **presidium and presidium-contrib are real, live, public PyPI packages**

```
pip install presidium          # 0.2.1
pip install presidium-contrib  # 0.2.0
```

Confirmed via a real, fresh-venv install and real imports — not assumed. GitHub Releases:
[`v0.2.1`](https://github.com/civitas-io/presidium/releases/tag/v0.2.1),
[`contrib-v0.2.0`](https://github.com/civitas-io/presidium/releases/tag/contrib-v0.2.0), both with
real CycloneDX SBOM assets attached.

**All five items of a P0 completion sequence are done** (see "Implementation Priority" in
`docs/vision/roadmap.md` for the original list and full detail on each):

1. **Real Ed25519 identity binding** — `GovernedRuntime.start()` previously hardcoded
   `public_key=""` despite being documented as delivered M2 behavior. Now generates/loads a real,
   persistent `AgentIdentity` per agent; `AgentRegistry` gained a real `verify_signature()`.
2. **`civitas` pinned to a real PyPI release** (`>=0.11.0`), not `git`/`branch="main"`.
3. **`presidium_contrib.service.policy`/`.registry` (Service Mode GenServers) 0% → 100% test
   coverage.**
4. **M7 "Presidium Server" — real, shipped.** `GovernedToolProvider.check_grant()` (a new,
   non-blocking, never-raising method in `presidium` core) + `presidium_contrib.server`
   (`PresidiumGatewayAgent`/`HealthCheckAgent`) expose governance over real REST+mTLS, satisfying
   `civitas-io/fabrica`'s `PresidiumClient.check_grant()` contract exactly. Verified end to end
   through an actual `civitas.gateway.HTTPGateway` and real `httpx` requests.
5. **`GovernedModelProvider`/`GovernedToolProvider` as drop-in Civitas `ModelProvider`/
   `ToolProvider`s.** New `presidium.providers.civitas_adapters` module
   (`GovernedModelProviderAdapter`/`GovernedToolAdapter`) + `GovernedRuntime.model_for()`/
   `tool_for()`, matching the real, already-established per-agent-construction precedent
   `civitas.process.AgentProcess.connect_mcp()` uses for `civitas-io/fabrica`'s own `MCPTool`.

**Real, current numbers**: 439 `presidium` tests (95.94% coverage), 162 `presidium-contrib` tests
(87% coverage, 0 xfails -- the mTLS handshake test's two previously-xfailed scenarios now pass for
real against the published `civitas>=0.11.3`), 3x stable, `ruff`/`mypy --strict` clean on both
packages' `src/` (the real, CI-gated scope).

---

## Approval list/decide over the network -- DONE, 2026-08-24, with an explicit scope boundary

Closes the second of `presidium-server.md`'s "Deferred: the fuller REST surface" items (registry
CRUD shipped first, same day). New `presidium_contrib.server.approval_agent`:
`ListApprovalsGatewayAgent` (`GET /v1/approvals`), `ApproveGatewayAgent`
(`POST /v1/approvals/{id}/approve`), `DenyGatewayAgent` (`POST /v1/approvals/{id}/deny`) --
exposing `ApprovalService.list_pending()`/`decide()` directly.

- **Deliberately no `POST /v1/approvals`** -- approval requests are created in-process by
  `GovernedToolProvider.check()`/`GovernedModelProvider.check()` calling `request_approval()`
  when a policy returns `REQUIRE_APPROVAL`, never by an external network caller (that would let
  a remote caller inject an arbitrary fake approval).
- **Real, honest, load-bearing scope boundary, confirmed by reading the source, not assumed**:
  `check_grant()` (the one real, existing HTTP-facing consumer via `PresidiumGatewayAgent`)
  does NOT call `ApprovalService.request_approval()` at all -- confirmed directly in
  `providers/tool.py`. It returns `REQUIRE_APPROVAL` as a plain value for the caller's own
  suspend/resume mechanism (FR-1.5), by design. This means an approval surfaced by
  `check_grant()` over `/v1/check_grant` is NOT tracked here and NOT resolvable through these
  new endpoints -- only approvals from the BLOCKING `check()` path (which does call
  `request_approval()`) are. Wiring `check_grant()`'s own `REQUIRE_APPROVAL` path into this is
  a real, separate, bigger integration (it would need to compose with Civitas's own durable
  suspension mechanism on the calling side, e.g. Fabrica) -- explicitly named as out of scope,
  not silently glossed over.
- **Also honest about `ApprovalService.decide()`'s own real contract**: it has no way to report
  "no such pending request" (confirmed against `CallbackApprovalProvider`'s own implementation
  -- a silent no-op for an unknown/already-resolved id) -- these endpoints reply
  `{"status": "decided", ...}` honestly rather than inventing a false-confidence 404 the
  underlying Protocol can't actually back up.
- Same "one real GenServer per HTTP route" pattern and `"reason"`-not-`"error"` reply-key
  convention as `registry_agent.py` (the real framework constraint found while building that
  one -- `civitas.gateway.dispatch.py` maps any reply with a top-level `"error"` key to a real
  HTTP 400).
- 13 new tests (`test_approval_agent.py` unit + `test_approval_gateway_real_http.py` real
  end-to-end HTTP), 100% coverage on the new file, `ruff`/`ruff format --check`/
  `mypy --strict` clean. Real fresh-venv install verified.

## M5 started: the first real `presidium` CLI -- DONE, 2026-08-24

Mirrors `civitas-io/python-civitas`'s own `civitas.cli` package structure exactly (Typer + Rich,
one module per command group, always-core not extra-gated typer/rich dependency). New
`presidium_contrib.cli` (`[project.scripts] presidium = "presidium_contrib.cli:main"`).

- **`presidium version`** -- shows both package versions (they genuinely drift apart, as this
  release proves: `presidium` 0.4.0, `presidium-contrib` 0.7.0).
- **`presidium registry list --db <path>`** -- lists agents from a local `SqliteRegistry` file
  (new `presidium-contrib[sqlite]` extra, forwarding to `presidium[sqlite]`). Deliberately not
  wired to a live `presidium-server`'s HTTP registry-CRUD endpoint yet -- a real, separate,
  named follow-up (`--server-url` mode).
- **`presidium policy validate <file>`** -- validates a CEL policy YAML file (standalone or
  topology-embedded), reporting every real error found (structural AND CEL compilation), not
  just the first, mirroring `civitas topology validate`'s own "show everything" UX. Reuses
  `presidium.runtime.parse_policy_rules()` (promoted from private to public specifically for
  this, so the CLI can't silently drift from what `GovernedRuntime.from_config()` actually
  accepts) and the real `CelPolicyEngine` for real compilation checking.
- **`presidium trust replay --events <file> --spec <file>`** (FR-5.3) -- wraps the real, pure,
  already-100%-tested `presidium.scoring.functions.replay()` directly.
- **Real, honest re-scoping, confirmed by reading the source first, not assumed**: FR-5.1's
  `trust show`/`trust events` (querying a LIVE agent's real history) are deliberately not built.
  No registry backend today persists a durable, queryable trust-event history --
  `LinearTrustScore` (the scorer every backend actually uses) keeps no event log at all;
  `WindowedTrustScorer` (which does use the real event-based scoring model) is pure in-memory
  and unused as any default. Building those two commands for real needs a durable event store
  first -- arguably M4's own job (FR-4.5, decision journal), not a CLI gap.
- **Two real bugs caught and fixed before shipping**: `SqliteRegistry`'s connection was never
  closed after `registry list` -- aiosqlite's background thread tried to call back into a
  closed event loop, a real, ugly traceback printed after otherwise-correct output. `trust
  replay`'s `--as-of` parsing sat OUTSIDE the command's own try/except, so an invalid value
  raised an unhandled exception instead of the same clean error every other malformed-input
  case gets.
- 18 new tests (`typer.testing.CliRunner`, real SqliteRegistry/YAML/JSON files, not mocked),
  86-100% coverage per file (remaining gaps are genuinely hard-to-trigger defensive branches --
  missing package metadata, missing `aiosqlite` -- matching this codebase's own established
  precedent for accepting those honestly). **Real, useful lesson re-confirmed**: never assert
  CLI tests on full Rich-rendered text substrings -- a long agent ID/file path wraps across
  table cells depending on terminal width, caught by a real, failing first test run, not
  assumed from `civitas.cli`'s own documented warning alone.

## Registry CRUD over the network -- DONE, 2026-08-24

Closes the design doc's own long-standing "Deferred: the fuller REST surface" item. New
`presidium_contrib.server.registry_agent`: `RegisterAgentGatewayAgent` (`POST /v1/agents`),
`ListAgentsGatewayAgent` (`GET /v1/agents`), `GetAgentGatewayAgent` (`GET /v1/agents/{name}`),
`DeregisterAgentGatewayAgent` (`DELETE /v1/agents/{name}`), `build_registry_gateway_config()`.
New `presidium_contrib/server/serialization.py` -- real `AgentRecord`/`Grant` JSON
(de)serialization, built from scratch (no such helper existed before).

- **Real, corrected design, not the original sketch**: one real GenServer per HTTP route, NOT
  the `payload["__op__"]` multi-op pattern the design doc originally proposed for this -- that
  exact pattern was already tried and rejected for check_grant/health during the earlier M7
  work (`payload_extra` is never populated for ordinary, user-declared routes).
- **Real, previously-unknown, load-bearing framework constraint found while implementing, not
  assumed**: `civitas.gateway.dispatch.py` classifies ANY reply payload containing a top-level
  `"error"` key as `DispatchStatus.AGENT_ERROR`, mapping to a real HTTP 400 -- regardless of
  whether anything actually raised. Caught this the hard way in a real end-to-end test (a
  "missing required field" reply I expected to be 200 came back 400). Every reply now uses
  `"reason"` instead, matching `PresidiumGatewayAgent`'s own pre-existing convention -- it had
  already avoided this pitfall, I just hadn't realized why until this.
- **Real, honest scope notes, not silently glossed over**: `GET /v1/agents` doesn't support
  `list_agents()`'s own status/trust_tier/owner filters (`civitas.gateway`'s dispatch never
  forwards a route's query string into a `mode: "call"` route's payload -- confirmed directly);
  grants are deliberately not settable via the register endpoint (a real, separate,
  not-yet-built grant-management endpoint); register is upsert, matching
  `AgentRegistry.register()`'s own real, existing behavior, not inventing new
  duplicate-detection/409-Conflict semantics.
- 15 new tests (`test_registry_agent.py` unit + `test_registry_gateway_real_http.py` real
  end-to-end HTTP, including a real, explicit proof that `GET`/`POST` on the same `/v1/agents`
  path route to two different agents correctly), 100% coverage on all three new/changed files,
  `ruff`/`ruff format --check`/`mypy --strict` clean. Real fresh-venv install verified.

## Rate limiting at the M7 network boundary -- DONE, 2026-08-24

Reuses Civitas's own first-party G4 rate limiter (`civitas.gateway.ratelimit.RateLimiter`/
`rate_limit` middleware -- sliding-window, per-client-IP) rather than building a second
mechanism, confirmed compatible by reading its source directly first.

- **`build_check_grant_gateway_config()` gained `rate_limit: bool = False`** -- opt-in, not
  opt-out, unlike `require_mtls`: an availability/operational control with real tuning
  implications, not a fail-closed security boundary.
- **New `build_rate_limiter()`** -- a thin constructor wrapper around
  `civitas.gateway.ratelimit.RateLimiter`, exposing `RATE_LIMITER_AGENT_NAME` (`"rate_limiter"`)
  so a caller doesn't need to discover, by reading Civitas's source, that the middleware's own
  lookup hardcodes that exact name (confirmed: an unregistered name raises `MessageRoutingError`
  immediately, not a silent fail-open or a 30s hang).
- **Real, load-bearing finding caught while implementing, not assumed**: global
  (`GatewayConfig.middleware`) and per-route (`RouteEntry.middleware`) middleware are
  *concatenated* per request, not deduplicated (confirmed directly against
  `civitas.gateway.asgi.py`'s own dispatch chain construction). Rate limiting is wired onto
  `/v1/check_grant`'s own per-route middleware specifically, never the global list or `/health`
  -- a liveness probe must never be rejected because real check_grant traffic used up the
  budget, and putting mTLS in both the global AND per-route list would have silently run it
  twice.
- **Verified end to end, not just at config-assembly level**: a real running gateway with a
  real, small budget (3 requests/window) genuinely returns `429` (with `Retry-After`) once
  exhausted, while `/health` keeps returning `200` throughout -- 4 new tests in
  `test_presidium_server_real_gateway.py`, including confirming the default is genuinely off.
  100% coverage on the changed file, `ruff`/`ruff format --check`/`mypy --strict` clean.

## `GovernedMcpToolPipeline` -- composes the three MCP governance primitives -- DONE, 2026-08-24

Before this, `PIIDetector`/`PoisoningDetector`/`redact_dict` were real, tested, shipped code with
**zero real composition** -- nothing in this codebase ever called them together, or from an
actual tool-call path at all. New `presidium_contrib.mcp_gateway.pipeline.GovernedMcpToolPipeline`
is the real implementation of `docs/design/mcp-gateway.md`'s own "Tool Poisoning Detection"/
"Credential Redaction"/"Output PII Masking" sections:

- **Poisoning check first, fail-closed by default** (`allow_unapproved_tools: bool = False`,
  matching this codebase's `allow_*` naming convention) -- an unapproved or changed tool blocks
  the call before the backend is ever reached. `list_tools()` tags each tool with its live
  `poisoning_status` as a real, additive enrichment.
- **Arguments redacted (`redact_dict`) before reaching `ActionRequest.parameters`** (today's
  earlier `scope`-threading work made this a real, usable hook) -- a CEL policy or audit log
  sees `"**REDACTED**"`, never the raw secret; the actual backend call still gets the real,
  unredacted arguments (the tool needs real values to function).
- **`PIIDetector.scan_dict()` enriches the result with `contains_pii`/`pii_pattern_names`
  before `post_check()` runs** -- opt-in by `pii_detector` presence (scanning every string in
  every result isn't free). A CEL POST_TOOL policy can now genuinely reference
  `result.contains_pii`, closing the real gap the design doc's own CEL example depended on but
  nothing ever populated. Verified end to end, not assumed.
- **Resolves the design doc's own open question** ("Should POST_TOOL modify results or only
  ALLOW/DENY?") differently than originally leaned -- not a new CEL decision type, but the
  pipeline's own separate, explicit `mask_pii_in_results` toggle (on by default) masking the
  value actually returned to the agent, independent of what CEL decided.
- 15 new tests (`tests/unit/mcp_gateway/test_pipeline.py`), 100% coverage on the new file,
  `ruff`/`ruff format --check`/`mypy --strict` clean.

**Real release gap found and named while verifying this, not silently ignored**: a real
fresh-venv install required building `presidium` from local source, not pip-installing the real
published PyPI package -- `presidium.providers.gateway` (this session's own earlier
AgentGatewayClient work) isn't in any released `presidium` version yet. Both `presidium` (last
real release v0.2.1) and `presidium-contrib` (v0.2.0) have accumulated substantial real,
unreleased functionality since -- tracked as its own new P1 roadmap item, not urgent but real.

## `AgentGatewayClient.delegate_to_agent()` (A2A half) -- DONE, 2026-08-24

Completes the `call_tool()`/`delegate_to_agent()` split from the earlier MCP-tool-side work,
same day. Real vendor research first
([`docs/design/a2a-delegation-vendor-research-2026-08.md`](docs/design/a2a-delegation-vendor-research-2026-08.md)):
confirmed the real `a2a-sdk` (`1.1.2`, official `a2aproject/a2a-python`) client API
(`create_client()`/`send_message()`/`get_stream_response_text()`) and the real, new,
load-bearing finding that **AgentGateway's A2A proxy routes per-upstream-agent** (one route per
agent server, agent-card URL rewriting) -- unlike MCP, there's no "resolve by agent name"
mechanism, which directly shaped the implementation.

- `AgentGatewayClient.__init__` gained `a2a_routes: dict[str, str] | None` -- an explicit
  target-agent-name -> gateway-route-URL map, supplied at construction.
- `delegate_to_agent()` maps `arguments["text"]` onto a real A2A text message (the only shape a
  text-only agent can respond to) or the whole dict onto a real A2A structured data message
  otherwise. Extracts the result via `get_stream_response_text()` (handles the completed-`Task`
  response shape the real reference agent actually produces, not just a bare `Message` reply).
- New `AgentGatewayDelegationError` for an unconfigured target (raised before any network call)
  or a terminal FAILED/REJECTED/CANCELED `TaskState`.
- **Verified end to end against a real running A2A server**
  (`tests/integration/fixtures/hello_a2a_server.py`) -- a faithful port of the real, official
  `a2a-samples` Hello World reference agent's exact `Task` lifecycle logic, not simplified
  (needed to genuinely exercise the completed-Task path). 6 new tests
  (`tests/integration/test_agentgateway_a2a_real_server.py`), not mocked, all passed on the
  first real run.
- 469 `presidium` tests pass, 183 `presidium-contrib` tests pass (+6), 96% coverage on the
  changed client file (two uncovered lines: a pre-existing, unrelated `call_tool()` branch, and
  a practically-untriggerable defensive-only guard), `ruff`/`ruff format --check`/
  `mypy --strict` clean. Real fresh-venv install verified both with and without
  `[agentgateway]`. New `a2a-sdk>=1.1.2` dependency on that extra.
- `docs/design/mcp-gateway.md` updated (the "MCP tool side DONE, A2A side deferred" framing
  corrected to reflect both being done); `roadmap.md`'s P1 checkbox flipped.

## Two P1 quick wins -- DONE, 2026-08-24

**`AGENTS.md` corrected.** It had drifted significantly since 2026-06-16: described
`litellm`/`kong`/`portkey`/`cloudflare_ai_gateway`/`helicone`/`truefoundry` as installable extras
with stub modules -- none of that code or those `pyproject.toml` extras exist (only
`AgentGateway` is a real, shipped `LLMGatewayBackend`). Also fixed: stale `presidium.protocols`/
`presidium.models` module names (real: distributed Protocols + singular `presidium.model`), a
stale "Pre-alpha (documentation-first phase)" status, a stale `Dependency Rules` claim
(`presidium` now also depends on `pynacl`/`cryptography`, not just `civitas`/`cel-python`), and
a monorepo tree missing `presidium.identity`/`presidium.lineage`/`presidium_contrib.spiffe`/
`presidium_contrib.server` entirely.

**`scope` (FR-1.4) now threaded through to `ActionRequest.parameters` -- a real, previously-
unfixed gap, not a new feature.** `presidium-server-requirements.md` documented this requirement
from the start, but `PresidiumGatewayAgent.handle_call()` read `agent_id`/`action` from the
request body and silently discarded `scope` entirely; `GovernedToolProvider.check_grant()`/
`check()`/`check_resource()` had no `parameters` parameter at all to receive it. Fixed: all three
methods gained an additive, optional `parameters: dict[str, Any] | None = None` (threaded
through the shared `_evaluate()` helper, so `check()`/`check_resource()` get it too, not just
`check_grant()`); the HTTP handler now reads `payload.get("scope")`, fail-closed DENYs (not a
5xx) if it's present but not a dict, and passes it straight through. Verified end to end, not
just at the unit level: real tests prove a CEL policy referencing `request.parameters.tenant_id`
actually sees the value that arrived in the HTTP request body's `scope` field, both allowing and
denying correctly.

469 `presidium` tests pass (+3), 178 `presidium-contrib` tests pass (+3), `ruff`/
`ruff format --check`/`mypy --strict` clean on both packages.

## Real, working pre-commit hooks -- installed, verified, not just configured

**2026-08-24**: `.pre-commit-config.yaml` existed here since June but the hook was never actually
installed. Now real: `uv run pre-commit install && uv run pre-commit install --hook-type
pre-push` wires up ruff/ruff-format/gitleaks on every commit, real per-package `mypy` and both
test suites on every push. `CONTRIBUTING.md` also substantially corrected while touching it --
it still described Presidium as pre-implementation, despite everything shipped this session.

## Real bugs found and fixed this session — read before assuming similar code elsewhere is correct

Every one of these was caught by an actual test run, a real running system, or a real fresh-venv
install — never by inspection alone. Worth knowing the *pattern*, not just the specific fixes:

- **`RegistryServer`'s own `self._registry` collided with `civitas.process.AgentProcess`'s own
  reserved `_registry` attribute** — a real `Supervisor` wiring it into a live tree would have
  silently clobbered one with the other. Found only after pinning `civitas` to a real PyPI release
  made its own `py.typed` marker visible for the first time, turning a previously-silent, overly
  broad `# type: ignore[misc]` into a real mypy failure.
- **`PolicyEvaluatorServer._handle_load()` stored a raw string instead of a `PolicyDecision`
  enum** — crashed on every non-default-ALLOW decision. 0% test coverage had hidden this entirely.
- **`check_grant()`'s shared helper silently inherited `check()`'s `"tool:"`-prefix convention** —
  broke the "resource = action, verbatim" requirement. Caught by the very first real test.
- **The original M7 design's `payload_extra`-based single-agent HTTP dispatch doesn't work** —
  `civitas.gateway.router.RouteTable.from_config()` never populates `payload_extra` for
  user-declared routes (it's exclusively Civitas's own internal topology-route mechanism). A real
  `GET /health` against the original design returned a real `400`. Fixed with one real agent per
  route instead.
- **A pre-existing, never-actually-run `publish.yml` had a real `uv build` output-path bug** —
  `working-directory: packages/presidium` + `uv build` places output in the *workspace root's*
  `dist/`, not the sub-package's. Confirmed with a real local build before trusting the workflow.
- **`import presidium` failed entirely without the `[sqlite]` extra** — found only because the
  release's own final verification step is a real fresh-venv install, not a formality. Shipped as
  an immediate `v0.2.1` patch fix.

---

## Update (2026-08-22, later same day): both AGT-comparison security gaps below are now DONE

**Trust ceiling propagation and monotonic capability narrowing are shipped** — new
`presidium.lineage` module, enforced inside `register()`/`add_grant()` on all three registry
backends (defense in depth, not an opt-in helper). New `AgentRecord.trust_ceiling`/`depth` fields;
`LinearTrustScore(ceiling=...)`; new `UnresolvableParentError`/`GrantEscalationError`/
`DelegationDepthExceededError`. 60+ new tests, 439 `presidium` + 162 `presidium-contrib` tests
pass 3x stable (0 xfails, since the mTLS work below). See `docs/log.md`'s 2026-08-22 "trust ceiling propagation + monotonic capability
narrowing" entry and `docs/vision/roadmap.md`'s own updated entries for full detail. Commit
`ddcbe91`.

## Default-deny for `CelPolicyEngine` — DONE, 2026-08-24

**The direction named above as "decided, not implemented" is now real, shipped code.** When no
policy rule matches for a stage, `CelPolicyEngine.evaluate()` now returns DENY/HARD by default,
not ALLOW -- the actual flip this doc used to describe as blocked by a 24-test blast radius.

- **Two real, explicit, loud opt-in knobs on `CelPolicyEngine.__init__`** (and forwarded through
  `presidium_contrib.service.policy.PolicyEvaluatorServer`), matching this codebase's own
  `allow_ungoverned`/`allow_unsandboxed` naming precedent, not a neutral, equally-weighted enum:
  `allow_unmatched_requests: bool = False` (restores the old always-ALLOW behavior outright) and
  `unmatched_enforcement: EnforcementMode = EnforcementMode.HARD` (lets a migrating deployment run
  the new DENY decision in `ADVISORY` mode first -- logged, not blocking -- before committing).
- **The real migration this forced, done properly, not shortcut**: every existing example/test
  policy set across `test_cel.py`, `test_governed_tool.py`, `test_governed_model.py`,
  `test_civitas_adapters.py`, `test_gateway_provider.py`, `test_governed_runtime.py`,
  `test_service_policy.py`, `test_gateway_agent.py`, `test_presidium_server_real_gateway.py`, and
  `test_service_mode_real_runtime.py` given an explicit terminal ALLOW rule (a new, shared
  `ALLOW_ALL` fixture in each package's own `tests/policy_fixtures.py` -- not shared cross-package,
  no existing precedent for that) -- the real, intended production pattern, not a test-only
  workaround. A few tests genuinely orthogonal to policy semantics (GenServer coexistence) use the
  `allow_unmatched_requests=True` shortcut instead, with a comment explaining why that's the right
  call there specifically.
- **`docs/design/policy-engine.md`'s own P5 decision corrected in place** (struck through, not
  deleted) with the real, empirical reasoning that overturned it: every existing policy set relied
  on the engine's own implicit ALLOW as an unwritten "cleared enforce-grants, no more objections ->
  allow" step -- the exact default-allow anti-pattern the original design was trying to avoid one
  level removed. `docs/guides/getting-started.md`'s own tutorial (both the programmatic and YAML
  examples) updated with a real, working explicit-ALLOW rule and a new "Default-deny" callout
  section -- this doc's own example would otherwise have silently denied everything now.
- 466 `presidium` tests pass (+8 net: several renamed/split to genuinely test the new behavior
  rather than just patched to keep passing), 175 `presidium-contrib` tests pass (+2), 100%
  coverage on both changed engine files, `ruff`/`mypy --strict` clean.

---

## What's next — the real, current P1 list (see roadmap.md for the full detail on each)

- LiteLLM + stub adapters (Kong/Portkey/Cloudflare AI Gateway/Helicone/TrueFoundry) — designed,
  evidence-based comparison exists, not built; explicitly not urgent (AgentGateway covers the
  reference path).
- M4 (Autonomy Progression), M5 (SDK+CLI, docs site, examples — now genuinely unblocked given
  real releases exist), M6 (Cloud, commercial) — all designed, none built.
- M8 (Performance Research: Rust vs. Python at the CEL policy-eval hot path) — correctly
  sequenced *after* M7 ships (which it now has), not before; real baseline numbers already
  measured (~88μs/~11,400 evals/sec per core, pure Python, GIL-bound — see roadmap.md).

## Working conventions established this session, worth continuing

- **Documentation-driven**: design docs (`docs/design/*-requirements.md` + `*.md` pairs) before
  implementation. `presidium-server-requirements.md`/`presidium-server.md` are the most recent,
  most complete example of the full pattern (requirements → design → real decisions recorded →
  implementation → design doc updated to match what was actually shipped).
- **Every real finding gets a `docs/log.md` entry**, dated, with the trigger, the real evidence,
  and what changed — this file is a better source of "what actually happened and why" than any
  single design doc read in isolation.
- **`docs/vision/roadmap.md`'s "Implementation Priority" section is orthogonal to the M-numbered
  milestones** — milestones are the scope source of truth; that section is the sequencing/urgency
  source of truth. Keep both in sync.
- **Real releases get real, immediate patch fixes when a real bug is found** — never left live and
  broken while a "proper" fix is planned (see the `v0.2.1` sqlite-import fix, shipped the same
  session it was found).
- **`civitas-io/context` gets updated after every real, cross-project-relevant finding** — not
  batched, not skipped for small findings.
