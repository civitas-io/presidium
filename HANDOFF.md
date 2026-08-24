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

## Real, decided-but-not-implemented — don't assume these are done

- **Default-deny for `CelPolicyEngine`'s no-rule-matched case.** Direction is explicitly decided
  (default DENY over ALLOW, for reduced blast radius, even at real UX cost) — but a real
  implementation attempt broke 24 existing tests and was reverted the same session. Every existing
  example/test policy assumes implicit allow-by-default; none declare an explicit terminal ALLOW
  rule. This needs its own dedicated design pass (see `docs/vision/roadmap.md`'s own entry for the
  exact scoped follow-up list) before touching it again.

---

## What's next — the real, current P1 list (see roadmap.md for the full detail on each)

- `AgentGatewayClient` missing `list_tools()`/`call_tool()` (MCP/A2A side; LLM side works)
- `presidium-contrib[spiffe]` (real SPIRE-issued X.509 SVIDs) — a separate, later upgrade to
  *agent-level* identity; not required for M7's own mTLS, which already works via a real,
  independent private CA
- LiteLLM + stub adapters (Kong/Portkey/Cloudflare AI Gateway/Helicone/TrueFoundry) — designed,
  evidence-based comparison exists, not built
- The two AGT-comparison security gaps above (trust ceiling, capability narrowing)
- Composing the three MCP governance primitives (PII/poisoning/redaction) into one real pipeline
- `scope` (from `check_grant`'s own contract) isn't yet threaded through to `ActionRequest.
  parameters` — CEL policies can't reference it from that path yet
- M4 (Autonomy Progression), M5 (SDK+CLI, docs site, examples), M6 (Cloud, commercial) — all
  designed, none built
- M8 (Performance Research: Rust vs. Python at the CEL policy-eval hot path) — correctly
  sequenced *after* M7 ships (which it now has), not before; real baseline numbers already
  measured (~88μs/~11,400 evals/sec per core, pure Python, GIL-bound — see roadmap.md)

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
