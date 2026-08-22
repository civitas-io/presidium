# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
