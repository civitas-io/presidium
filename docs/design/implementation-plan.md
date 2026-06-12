# M2 Implementation Plan

> Phased build order, dependency graph, verification strategy, and module layout for Presidium M2.
> Status: Phases 1-6 implemented. 234 tests, 95% coverage. Civitas integration remaining.
> Prerequisite: All design docs reviewed and approved (12/12 issues resolved)

## Overview

M2 delivers `pip install presidium` — complete library-mode governance. 9 components, ~2,900 lines of specification, 35 design decisions. This plan defines the order in which components are built, what proves each phase works, and the package layout.

**Total effort estimate:** ~10-14 dev-days solo, ~6-8 days with two devs exploiting per-phase parallelism.

---

## Dependency Graph

```
                   ┌──────────────────────────────┐
                   │  #1 Data model (AgentRecord,  │
                   │  Grant, TrustTier, enums)     │
                   └────┬────┬────┬────┬──────────┘
                        │    │    │    │
              ┌─────────┘    │    │    └─────────────┐
              ▼              ▼    ▼                  ▼
        #2 TrustScorer  #5 Policy*  #7 Credentials  #13 Civitas
              │              │           │           changes
              ▼              ▼           │           (independent)
        #3 InMemory     #6 CEL    #8 Approval
        Registry        Engine      │
              ├──────┐       │      │
              ▼      ▼       │      │
        #4 SQLite  #9 Audit  │      │
                     ▲       │      │
                     │       ▼      ▼
                     └── #10 GovernedModel
                         #11 GovernedTool
                                │
                                ▼
                         #12 GovernedRuntime
```

No cycles. `#4 SqliteRegistry` and `#9 AuditEnricher` are NOT on the critical path — InMemoryRegistry + a stub audit sink suffice for a working GovernedRuntime.

---

## Phase 1: Foundation + Risk Spike (~0.5 day)

### Build
- `model.py` — all data model types:
  - `AgentStatus` enum (REGISTERED, STARTING, RUNNING, STOPPING, STOPPED, SUSPENDED)
  - `TrustTier` enum (TRUSTED, STANDARD, RESTRICTED)
  - `TrustEvent` enum (SUCCESS, FAILURE, POLICY_VIOLATION, HUMAN_OVERRIDE)
  - `Grant` dataclass (resources, actions, scope, condition, expires_at, id)
  - `AgentRecord` dataclass (agent_id, name, public_key, grants, trust_value, trust_tier, status, owner, parent_agent_id, description, agent_version, capabilities, metadata, revision, created_at, updated_at)
  - `PolicyDecision` enum (ALLOW, DENY, REQUIRE_APPROVAL)
  - `EvaluationStage` enum (PRE_TOOL, PRE_LLM, REGISTRATION)
  - `EnforcementMode` enum (ADVISORY, SOFT, HARD)
  - `ApprovalStatus` enum (PENDING, APPROVED, DENIED, TIMED_OUT)

### Risk Spike (throwaway, not committed)
- 30-line script that: (a) evaluates one CEL expression with `cel-python` against a fake context dict, (b) instantiates a Civitas `AuditSink` and emits one event. Confirms both external deps behave as expected before committing to Protocol shapes.

### Verify
- Dataclass construction, equality, frozen-field invariants
- Enum exhaustiveness
- Grant condition field accepts CEL strings
- AgentRecord agent_id accepts `presidium://` URIs
- JSON serialization round-trip for persistence

### Done when
- `from presidium import AgentRecord, Grant, PolicyDecision, TrustTier` works
- All unit tests pass
- CEL spike confirms `cel-python` evaluates expressions against dicts

---

## Phase 2: Core Abstractions (~2 days, parallelizable 4-wide)

### Build (in parallel)

**2a. TrustScorer** (`trust.py`)
- `TrustScorer` Protocol (value, tier, last_updated, record_event)
- `LinearTrustScore` implementation (lazy-on-read decay, materialize-on-write)

**2b. PolicyEngine Protocol** (`policy/_base.py`)
- `PolicyRule` dataclass (name, stage, expression, decision, reason, priority, enforcement, approvers, enabled)
- `PolicyResult` dataclass (decision, policy_name, reason, approvers, enforcement)
- `ActionRequest` dataclass (resource, action, parameters)
- `EvaluationContext` dataclass (agent, request, time)
- `PolicyEngine` Protocol (load_policies, evaluate)

**2c. CredentialProvider** (`credentials.py`)
- `CredentialProvider` Protocol (get, close)
- `EnvCredentialProvider` (grant check + os.environ lookup + audit)
- `FileCredentialProvider` (grant check + key=value file + audit)

**2d. Civitas changes** (in `python-civitas` repo)
- Add `"presidium"` to `_KNOWN_CONFIG_KEYS`
- Refactor `from_config()` to extract `from_config_dict()` classmethod

### Verify
- Trust: golden tests for boundary values (0.0, 1.0), tier transitions (0.29→RESTRICTED, 0.3→STANDARD, 0.7→TRUSTED), decay math, event recording
- Policy: Protocol conformance via `runtime_checkable`, `FakePolicyEngine` that returns canned results
- Credentials: env provider reads from `os.environ`, file provider parses key=value, grant check denies without matching grant, audit events emitted
- Civitas: existing tests still pass, `from_config_dict()` produces identical runtime to `from_config()`

### Done when
- All Protocols importable: `from presidium import TrustScorer, PolicyEngine, CredentialProvider`
- Trust math is proven correct with table-driven tests
- Civitas CI passes with the 2 additions

---

## Phase 3: Primary Implementations (~2.5 days, parallelizable 3-wide)

### Build (in parallel)

**3a. InMemoryRegistry** (`registry/memory.py`)
- `AgentRegistry` Protocol definition (`registry/_base.py`)
- `InMemoryRegistry` — dict-backed, snapshot semantics on lookup, revision counter, trust delegation to `LinearTrustScore`
- `trust_events` list storage (append-only, for M4 compatibility)

**3b. CelPolicyEngine** (`policy/cel.py`)
- Compile CEL expressions at load time (fail-fast on bad expressions)
- Evaluate per-stage in priority order (first-match-wins)
- Grant pre-filtering (expired + false conditions removed before evaluation)
- Fail-closed on evaluation errors
- Multi-stage rule support (stage as list)
- Wrap `cel-python` exceptions in `PolicyEvaluationError`

**3c. CallbackApprovalProvider** (`approval.py`)
- `ApprovalService` Protocol (request_approval, list_pending, decide)
- `ApprovalRequest` and `ApprovalDecision` dataclasses
- `CallbackApprovalProvider` — auto_approve/auto_deny modes, callback function, manual mode with asyncio.Future + timeout
- Fail-closed on timeout (auto-deny)

### Verify
- Registry: CRUD operations, lookup returns immutable snapshot, revision increments, trust events recorded, `asyncio.gather` 100 concurrent writers (stress test)
- CelPolicyEngine: ≥10 fixture policies covering ALLOW/DENY/REQUIRE_APPROVAL, malformed expressions raise `PolicyEvaluationError`, fail-closed on eval error, multi-stage rules, enforcement modes, grant pre-filtering, eval latency < 5ms p99
- Approval: timeout auto-denies, callback success/failure, cancellation, pending list, decide resolves future

### Done when
- `InMemoryRegistry` passes full CRUD + concurrency tests
- `CelPolicyEngine` evaluates all fixture policies correctly
- `CallbackApprovalProvider` handles all approval flows
- ≥85% coverage on all three modules

---

## Phase 4: Audit Integration (~1 day)

### Build
- `AuditEnricher` Protocol (`audit.py`)
- `InProcessAuditEnricher` — middleware wrapping downstream `AuditSink`, cached registry lookups (5s TTL), re-enrichment guard, governance context under `details["governance"]`

### Verify
- Enriched events contain registry-sourced fields (agent_id, trust_value, trust_tier, owner)
- Events with existing `governance` key forwarded without re-enrichment
- Cache TTL respected (stale after 5s)
- Downstream sink receives all events (none dropped)
- Enrichment errors logged but event forwarded (fail-open)
- Use `RecordingAuditSink` fake for assertions

### Done when
- AuditEnricher correctly enriches Civitas events and passes through Presidium events
- ≥85% coverage

---

## Phase 5: Governed Providers (~2 days, parallelizable 2-wide)

### Build (in parallel)

**5a. GovernedModelProvider** (`providers/model.py`)
- Wraps Civitas `ModelProvider`
- Evaluates `PRE_LLM` policies before delegating
- ALLOW → delegate, DENY → raise `PolicyDeniedError`, REQUIRE_APPROVAL → route to ApprovalService
- Emits `policy.evaluated` audit events

**5b. GovernedToolProvider** (`providers/tool.py`)
- Wraps Civitas `ToolProvider`
- Evaluates `PRE_TOOL` policies before delegating
- Same ALLOW/DENY/REQUIRE_APPROVAL flow as GovernedModelProvider
- Emits `policy.evaluated` audit events

### Verify
- Three paths per provider (allow, deny, require_approval) using fake model/tool
- Audit events emitted for every evaluation
- Advisory mode logs but doesn't block
- Soft mode warns but doesn't block
- Hard mode blocks on DENY
- ApprovalService integration: suspends, resumes on approve, raises on deny/timeout

### Done when
- Both providers handle all three policy decisions correctly
- Fake model/tool calls proceed only when allowed
- ≥85% coverage

---

## Phase 6: Runtime + SQLite Backend (~3 days)

### Build

**6a. GovernedRuntime** (`runtime.py`)
- `GovernedRuntime.from_config()` — read YAML, extract `presidium:` block, pass rest to `Runtime.from_config_dict()`
- Build governance components from config
- Register per-agent governance data (owner, grants from `presidium.agents` block)
- Wrap Civitas components (ModelProvider → GovernedModelProvider, ToolProvider → GovernedToolProvider, AuditSink → AuditEnricher)
- Delegate start/stop/ask/send to Civitas Runtime
- Programmatic constructor for non-YAML usage

**6b. SqliteRegistry** (`registry/sqlite.py`)
- Same Protocol as InMemoryRegistry, SQLite backend
- `agent_records` + `trust_events` tables
- WAL mode + `BEGIN IMMEDIATE` for write serialization
- `aiosqlite` for async I/O

**6c. Public API** (`__init__.py`)
- Curated exports: all Protocols, all default implementations, GovernedRuntime, data model types

### Verify
- Runtime: 2-3 end-to-end scenarios with a real Civitas Runtime:
  1. Compliant agent with matching grants → tool call succeeds
  2. Low-trust agent without grant → tool call denied
  3. Approval-gated action → suspends, approves, completes
- SqliteRegistry: re-run the ENTIRE Phase 3 registry test suite parametrized over both backends (one fixture, two registries). Cheapest way to guarantee parity.
- YAML loading: topology with `presidium:` block parsed correctly, agents registered with correct grants

### Done when
- `GovernedRuntime.from_config("topology.yaml")` starts a governed runtime
- End-to-end scenarios pass
- SqliteRegistry passes all InMemoryRegistry tests
- `pip install .` from the package root works
- ≥85% overall coverage

---

## Package Layout

```
packages/presidium/
├── pyproject.toml                  # hatchling, deps: cel-python, civitas
├── README.md
├── src/presidium/
│   ├── __init__.py                 # curated public API
│   ├── model.py                    # Phase 1: AgentRecord, Grant, all enums
│   ├── trust.py                    # Phase 2: TrustScorer Protocol, LinearTrustScore
│   ├── credentials.py              # Phase 2: CredentialProvider Protocol + Env/File impls
│   ├── approval.py                 # Phase 3: ApprovalService Protocol + CallbackApprovalProvider
│   ├── audit.py                    # Phase 4: AuditEnricher Protocol + InProcessAuditEnricher
│   ├── runtime.py                  # Phase 6: GovernedRuntime
│   ├── errors.py                   # PresidiumError base, PolicyDeniedError, etc.
│   ├── registry/
│   │   ├── __init__.py             # AgentRegistry Protocol (re-export from _base)
│   │   ├── _base.py                # Protocol definition
│   │   ├── memory.py               # Phase 3: InMemoryRegistry
│   │   └── sqlite.py               # Phase 6: SqliteRegistry
│   ├── policy/
│   │   ├── __init__.py             # PolicyEngine Protocol, PolicyRule, Result, Context
│   │   ├── _base.py                # Protocol + data types
│   │   └── cel.py                  # Phase 3: CelPolicyEngine
│   └── providers/
│       ├── __init__.py
│       ├── model.py                # Phase 5: GovernedModelProvider
│       └── tool.py                 # Phase 5: GovernedToolProvider
└── tests/
    ├── conftest.py                 # shared fixtures: fake sinks, sample agents, sample grants
    ├── unit/
    │   ├── test_model.py           # Phase 1
    │   ├── test_trust.py           # Phase 2
    │   ├── test_credentials.py     # Phase 2
    │   ├── test_approval.py        # Phase 3
    │   ├── test_audit.py           # Phase 4
    │   ├── registry/
    │   │   ├── conftest.py         # parametrized `registry` fixture (memory + sqlite)
    │   │   └── test_registry.py    # one suite, both backends
    │   ├── policy/
    │   │   ├── fixtures/           # .yaml policy files for test cases
    │   │   └── test_cel.py         # Phase 3
    │   └── providers/
    │       ├── test_governed_model.py  # Phase 5
    │       └── test_governed_tool.py   # Phase 5
    └── integration/
        ├── test_governed_runtime.py    # Phase 6: end-to-end with Civitas
        └── test_civitas_compat.py      # Phase 6: Civitas from_config_dict smoke test
```

**Rationale**: `registry/` and `policy/` are packages because they have multiple implementations behind a Protocol. Everything else is a single module. The parametrized registry test suite in Phase 6 guarantees SQLite parity with InMemory for free.

---

## Risk Mitigation

| Risk | Mitigation | Phase |
|---|---|---|
| `cel-python` doesn't work as expected | Phase 1 spike validates assumptions before Protocols are finalized | 1 |
| Protocol shape wrong after multiple consumers depend on it | Review PolicyEngine and AgentRegistry Protocols at Phase 2 gate before Phase 3 begins | 2→3 gate |
| CelPolicyEngine latency exceeds 5ms | Benchmark in Phase 3. If too slow, consider caching compiled programs or evaluating pre-filtering optimization. | 3 |
| SqliteRegistry concurrent access issues | Use WAL mode + asyncio.Lock for single-writer. Document library mode as single-process. | 6 |
| `cel-python` exceptions leak to user code | Wrap in `PolicyEvaluationError` at the boundary in Phase 3 | 3 |

---

## Phase Gates

Each phase has a gate — a checkpoint before proceeding to the next phase.

| Gate | Condition | Who Reviews |
|---|---|---|
| Phase 1 → 2 | Data model tests pass. CEL spike confirms `cel-python` works. | Self-review |
| Phase 2 → 3 | All Protocols importable. Trust math proven. Civitas changes pass CI. **Protocol shape reviewed.** | Design review |
| Phase 3 → 4 | Registry CRUD + concurrency tests pass. CEL evaluates all fixtures. Approval timeout works. ≥85% coverage. | Self-review |
| Phase 4 → 5 | Enricher enriches correctly, passes through Presidium events, fail-open works. | Self-review |
| Phase 5 → 6 | Both governed providers handle all 3 policy decisions. Audit events emitted. | Self-review |
| Phase 6 → Done | End-to-end scenarios pass. SqliteRegistry parity proven. `pip install .` works. ≥85% overall coverage. | Full review |

---

## Testing Strategy

### Unit Tests (per-module, ≥85% coverage)
- Table-driven tests for math (trust decay, tier boundaries)
- Fixture-based tests for CEL policies (YAML files with expected results)
- Parametrized registry tests (one suite, both backends)
- Fake/mock Civitas components (FakeModelProvider, FakeToolProvider, RecordingAuditSink)

### Integration Tests (end-to-end, Phase 6)
- Real Civitas Runtime with GovernedRuntime wrapper
- Real agents (simple AgentProcess subclasses) with governance applied
- Scenarios: allow, deny, require_approval, trust decay, credential access

### What We DON'T Test in M2
- Service mode (M3)
- OPA/Cedar/Vault adapters (M3)
- Multi-process concurrency (M3)
- Performance benchmarks (track but don't gate on — benchmark in Phase 3)

---

## Dependencies

### External (pip)
- `civitas` — the runtime we're governing
- `cel-python` — CEL expression evaluation
- `aiosqlite` — async SQLite for SqliteRegistry

### Dev
- `pytest` + `pytest-asyncio` — testing
- `ruff` — linting + formatting
- `mypy` — type checking (strict mode)
- `coverage` — ≥85% enforcement

---

## Timeline Summary

| Phase | What | Effort | Parallelism |
|---|---|---|---|
| 1 | Data model + CEL spike | 0.5 day | — |
| 2 | Protocols + defaults (Trust, Policy, Creds, Civitas) | 2 days | 4-wide |
| 3 | Implementations (Registry, CEL, Approval) | 2.5 days | 3-wide |
| 4 | Audit enricher | 1 day | — |
| 5 | Governed providers (Model, Tool) | 2 days | 2-wide |
| 6 | GovernedRuntime + SqliteRegistry + integration tests | 3 days | — |
| **Total** | | **~11 days solo** | **~7 days with 2 devs** |
