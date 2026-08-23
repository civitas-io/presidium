# Handoff: Presidium

**Purpose of this doc:** resume work cold, after a context compaction, without re-deriving
anything already decided. Read this first, then follow the links — don't re-read the whole repo
linearly. Deep, dated engineering history (every finding, every real decision, why) lives in
[`docs/log.md`](docs/log.md); the ordered work queue lives in
[`docs/vision/roadmap.md`](docs/vision/roadmap.md)'s own "Implementation Priority" section.

**Cross-project context**: this project is one of three real pillars in the `civitas-io` org
(Civitas = runtime, Presidium = this repo, governance, Fabrica = context layer). The private
`civitas-io/context` repo is the cross-repo reasoning substrate — `projects/presidium.md` there
mirrors everything below in more narrative form, kept in sync after every real change.

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

**Real, current numbers**: 439 `presidium` tests (95%+ coverage), 158 `presidium-contrib` tests
(87% coverage), 3x stable, `ruff`/`mypy --strict` clean on both packages' `src/` (the real,
CI-gated scope).

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
`DelegationDepthExceededError`. 60+ new tests, 439 `presidium` + 158 `presidium-contrib` tests
pass 3x stable. See `docs/log.md`'s 2026-08-22 "trust ceiling propagation + monotonic capability
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
