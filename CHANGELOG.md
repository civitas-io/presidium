# Changelog

All notable changes to this project are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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
