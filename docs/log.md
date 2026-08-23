# Wiki Log

> Append-only chronological record of wiki operations.
> Each entry uses the format: `## [YYYY-MM-DD] operation | description`
> Parseable with: `grep "^## \[" docs/log.md | tail -10`

---

## [2026-04-30] init | Repository created with documentation-first approach

**Sources ingested:**
- python-civitas repository (GitHub: jerynmathew/python-civitas) — evaluated architecture, code quality, documentation, testing, security
- Microsoft Agent Governance Toolkit — evaluated as competitor, 540K LOC, 9 packages, 10/10 OWASP
- Fiddler AI product pages and Series C announcement — evaluated as complement, $100M funding
- LangChain Series B announcement ($125M, $1.25B valuation)
- CrewAI funding and product data ($18M Series A, $3.2M ARR)
- Temporal Series D announcement ($300M, $5B valuation)
- Work-Bench "Rise of the Agent Runtime" research (Feb 2026)
- Multiple market analysis reports (Gartner, TURION.AI, RAYSolute, Technavio, Markets NXT, IDC)
- Multiple production failure analysis articles (Paperclipped, Agentuity, Viqus, NeuralWired, iBuidl)
- Karpathy LLM Wiki pattern (gist, 5000+ stars)

**Pages created:** 22 documents across vision/, architecture/, design/, research/, rfcs/

**Key decisions:**
- Presidium positioned as "governed runtime" (not "control plane" — avoids Fiddler branding collision)
- Complementary to Fiddler (generates telemetry, Fiddler analyzes)
- Python ≥3.12 (compatibility over cutting-edge)
- uv workspaces + hatchling (matching civitas-forge conventions)
- Documentation-first: design docs before code

## [2026-04-30] update | Mermaid diagrams and email fixes

**Changes:**
- Replaced all ASCII box-drawing diagrams with MermaidJS (renders natively on GitHub)
- 8 diagrams converted: architecture overview, data flow, package dependency graph, competitive quadrant chart, agent state machine, eval feedback loop, stack layers, data pipeline
- Fixed author email to jerynmathew@gmail.com
- Fixed security contact email

## [2026-04-30] update | Wiki maintenance system adopted

**Changes:**
- Adopted Karpathy's LLM Wiki pattern for persistent knowledge management
- Enriched docs/index.md into full wiki catalog with per-page summaries
- Created docs/log.md (this file) for chronological operation tracking
- Added Ingest/Query/Lint workflows to AGENTS.md § Wiki Maintenance
- Wiki is now a living artifact — AI assistants know how to maintain it

## [2026-05-08] update | Eval framework redesign + DeepEval integration + test harness

**Sources ingested:**
- DeepEval documentation and source code (GitHub: confident-ai/deepeval) — 50+ built-in metrics, BaseMetric custom metrics, LLMTestCase, pytest integration via assert_test(), EvaluationDataset for golden management
- Civitas evalloop.py source (EvalAgent, EvalExporter protocol, EvalEvent, CorrectionSignal with nudge/redirect/halt severities)
- Civitas __init__.py public surface (confirms EvalAgent, EvalEvent, EvalExporter, CorrectionSignal are all public API)
- Team feedback: implement evaluations, test harness, and DeepEval support as general civitas infrastructure (not example-specific)

**Pages revised:**
- `docs/design/eval-framework.md` — Major rewrite. Previously a thin sketch (116 lines). Now a full design doc covering:
  - Two-tier architecture (in-flight via EvalAgent + offline via pytest test harness)
  - GovernanceEvalAgent with composite scoring (governance + quality → trust feedback)
  - GovernanceMetrics dataclass expanded (drift_score, grant_violation_count added)
  - MetricRegistry for shared metric config between in-flight and offline
  - EvalTestRunner, EvalDataset, EvalTestCase types for civitas[test] extra
  - Flight recorder AuditSink for capturing production traces as golden datasets
  - Feedback loop documentation (eval → trust → autonomy → policy)
  - Open questions updated with concrete proposals
- `docs/architecture/packages.md` — presidium-eval section to be updated
- `docs/index.md` — Added DeepEval Integration entry, updated Eval Framework status to "Draft (revised)", added architecture diagrams entry

**Pages created:**
- `docs/design/deepeval-integration.md` — Companion design doc for civitas-contrib[deepeval]:
  - DeepEvalExporter implementation (EvalExporter → LLMTestCase bridge)
  - EvalEvent payload contract specification
  - Score-to-CorrectionSignal mapping utility
  - 6 recommended built-in DeepEval metrics with thresholds
  - 2 custom BaseMetric implementations (ScopeDriftMetric, BudgetAdherenceMetric)
  - In-flight latency analysis (deterministic vs LLM-as-Judge)
  - Offline harness integration with deepeval test run
  - Plugin loader YAML configuration
  - Module layout for civitas-contrib

**Assets created:**
- `docs/assets/eval-architecture.svg` — Two-tier eval architecture diagram (in-flight + offline, package ownership legend)
- `docs/assets/deepeval-integration.svg` — DeepEval data flow (EvalEvent → LLMTestCase → metrics → CorrectionSignal, package boundary table)
- `docs/assets/test-harness-architecture.svg` — Test harness flow (dataset sources → EvalTestRunner → DeepEval metrics → CI gate)

**Key decisions:**
- DeepEval is recommended, not required — architecture is backend-agnostic via EvalExporter protocol
- Test harness lives in civitas core (civitas[test] extra), not in presidium — any Civitas agent can use it
- DeepEvalExporter lives in civitas-contrib[deepeval], same pattern as provider implementations
- Governance metrics live in presidium-eval — they depend on registry + policy
- Same metric instances run in-flight and offline — single source of truth, no threshold drift
- Deterministic metrics always run in-flight; LLM-as-Judge metrics are sampled or async
- Flight recorder (AuditSink) captures production traces as golden datasets

## [2026-06-11] architecture | Interface-first redesign + CEL + library/service dual mode

**Sources ingested:**
- Analysis of Civitas codebase for coding agent and autonomous agent feasibility
- CEL (Common Expression Language) specification and Kubernetes adoption patterns
- Comparison of OPA/Rego vs CEL for embedded policy evaluation
- Survey of existing products for governance components (OPA, Vault, LiteLLM Proxy, Slack, Temporal, PagerDuty)

**Pages revised:**
- `README.md` — Rewritten to reflect interface-first strategy, 2-package structure, CEL default, library-vs-service modes, build-vs-wrap table
- `AGENTS.md` — Updated monorepo structure, package boundaries, dependency rules, glossary (CEL, Interface Library, Adapter, Reference Implementation, Library Mode, Service Mode), anti-patterns
- `docs/architecture/packages.md` — Full rewrite. 6-package structure replaced with `presidium` (protocols + CEL) + `presidium-contrib` (adapters + reference impls). Component map table, Protocol definitions for all 8 components, Mermaid dependency graph.
- `docs/architecture/overview.md` — Updated Mermaid diagrams for 2-package structure. Added 3 new design decisions: Interface-First Architecture, CEL as Default Policy Language, Library-First Service-Optional. Updated data flow for inline CEL evaluation.
- `docs/architecture/stack.md` — Deployment scenarios rewritten with library/service distinction and YAML topology examples per scenario.
- `docs/vision/roadmap.md` — Milestones revised: M1 complete; M2 renamed "Core Interfaces + CEL Policy" (all Protocols + library defaults); M3 renamed "Contrib Adapters + Reference Impls"; new M4 "Autonomy Progression" (decision journal, confidence routing, learned trust); M5/M6 updated.
- `docs/index.md` — Summaries updated for all revised architecture pages. Design doc table updated with new package references.

**Cross-repo changes (python-civitas):**
- `docs/design/civitas-presidium-boundary.md` — Appended "Presidium Architecture: Interface-First with Dual Deployment Modes" section: 2-package structure, CEL rationale, library/service modes with YAML examples, product mapping table, autonomy progression (4 levels).
- `docs/milestones.md` — Phase 5 intro rewritten to reference Presidium interface-first architecture. LLM Gateway entry updated from `presidium-llm-gateway` to `GovernedModelProvider` protocol + `presidium-contrib` adapters.
- `README.md` — CONTROL LAYER box updated to name Presidium and CEL/OPA.

**Key decisions:**
- 6-package structure (`presidium-registry`, `presidium-policy`, etc.) replaced with 2-package structure (`presidium` + `presidium-contrib`), mirroring the `civitas` + `civitas-contrib` pattern
- CEL (Common Expression Language) chosen as default policy engine over OPA/Rego: embeddable (in-process, microseconds), no sidecar, Kubernetes direction, simpler expressions, cel-python exists. OPA available as `presidium-contrib[opa]` adapter.
- Every component has library mode (in-process, no infrastructure) and optional service mode (GenServer or HTTP, for distributed deployments). Library mode is the complete implementation, not a degraded subset.
- Where mature products exist (OPA, Vault, LiteLLM, Slack, Temporal), Presidium wraps them as adapters. Where nothing exists (Agent Registry with grants+trust, MCP governance, Trust scoring), Presidium builds reference implementations.
- Autonomy progression: HITL → heuristic recommendations → learned partial autonomy → full autonomy. Levels 1-2 work with current Civitas + Presidium interfaces. Levels 3-4 require decision journal and confidence routing (M4).

## [2026-06-11] research | Agent registry industry research across 4 streams

**Sources researched:**
- AWS Bedrock Agents API (CreateAgent, GetAgent, Action Groups, Guardrails, AgentCore Cedar policies)
- AWS IAM (policy documents, trust policies, Roles Anywhere, condition operators)
- Google Gemini Enterprise Agent Platform (Agent Registry, Agent Identity, Auth Manager)
- Google Zanzibar / AuthZed SpiceDB (relationship tuples, schema language, zookies)
- GCP IAM (Service Accounts, Workload Identity Federation)
- Google ADK (Agent Development Kit, Agent Engine API)
- Microsoft AGT Agent Mesh source code (identity, trust decay, privilege rings, policy engine)
- Microsoft Entra Agent ID (agent identity governance)
- IBM watsonx Orchestrate (agent registry API, CUGA governance architecture)
- IBM Research: Governance by Construction (CUGA paper)
- SPIFFE specification (SPIFFE ID format, X.509-SVID, JWT-SVID, trust domains, federation)
- SPIRE (attestation, registration entries, identity rotation)
- Kubernetes RBAC (ServiceAccount, Role, RoleBinding, admission webhooks)
- Kubernetes Workload Identity (GKE, EKS federation)
- OAuth 2.0 Client Credentials (scopes as grants)
- 4 academic papers: Auditable Agents (arXiv:2604.05485), Overlaying Governance (arXiv:2606.03518), Governing Dynamic Capabilities (arXiv:2603.14332), AGENTSAFE (arXiv:2512.03180)

**Pages created:**
- `docs/research/agent-registry-research.md` — comprehensive research synthesis with comparative analysis table and 8 key design patterns

**Pages updated:**
- `docs/index.md` — added research entry

**Key findings:**
- Every major system separates identity from authorization (universal pattern)
- Google shipped a centralized Agent Registry in Gemini Enterprise — closest prior art
- Microsoft AGT has the most mature trust scoring (0-1000, 5 tiers, 5 dimensions, decay + contagion)
- SPIFFE/SPIRE is purpose-built for ephemeral workloads (matches Civitas agent lifecycle)
- Kubernetes RBAC has the cleanest 3-object separation (identity, authorization, binding)
- Zanzibar ReBAC is more powerful than flat grants but may be over-engineering for M2
- Human sponsor requirement appears in both AGT and Entra (enterprise necessity)
- Fail-closed policy evaluation (AGT) prevents exception-based bypass

## [2026-06-11] design | Agent registry requirements document

**Pages created:**
- `docs/design/agent-registry-requirements.md` — functional and non-functional requirements for the AgentRegistry, informed by industry research. 9 functional requirement groups (registration, grants, trust, spawning, lifecycle, querying, persistence, auth, audit), 3 NFRs, 6 resolved design decisions.

**Pages updated:**
- `docs/index.md` — added requirements doc entry

**Key decisions resolved:**
- D1: K8s-style grants with CEL condition field (evolvable toward ReBAC)
- D2: Human sponsor schema-optional, policy-enforced (CEL-based, mode-dependent defaults)
- D3: Trust scoring 0.0-1.0 with 3 tiers, Protocol for swapping implementations
- D4: Spawning: subset grants enforced, trust independent (not inherited), lineage tracked
- D5: Revision counter + optional agent_version metadata
- D6: Trust-the-runtime (library) + message-bus-signing (service), Protocol for SPIFFE later

## [2026-06-11] design | SPIFFE-compatible identity model + CNCF standards principle

**Key decisions:**
- D7: Agent identity format changed from UUID to SPIFFE-compatible URI: `presidium://{trust_domain}/{path}` with Ed25519 cryptographic binding
- UUID rejected as opaque and meaningless — cannot self-verify, carries no trust domain or lineage info
- DID (Microsoft AGT approach) rejected as lacking trust domain scoping
- Raw SPIFFE (spiffe://) rejected for M2 as requiring SPIRE infrastructure — but format is compatible for M3+ upgrade
- Lineage encoded in URI path: parent `presidium://acme.com/prod/orchestrator` → child `presidium://acme.com/prod/orchestrator/child/worker-3`
- Ed25519 keys from Civitas (M4.2a) reused for identity binding — no new crypto infrastructure

**Design principle added:**
- CNCF standards preference adopted as a project-wide principle: SPIFFE for identity, OTEL for observability, CEL for policy
- Added to AGENTS.md (What Presidium Is), RFC-001 (Design Principles), and README.md (CNCF-Aligned Standards section)

**Pages updated:**
- `AGENTS.md` — CNCF alignment added to "What Presidium Is"
- `README.md` — new "CNCF-Aligned Standards" section added
- `docs/rfcs/001-presidium-scope.md` — CNCF alignment added to Design Principles
- `docs/design/agent-registry.md` — AgentRecord identity model, identity format section, SQL schema, design decisions table, audit examples, dynamic spawning lineage
- `docs/design/agent-registry-requirements.md` — FR-1 updated (1.6-1.9), scenarios, NFR-4 CNCF alignment, D7, out-of-scope updated

## [2026-06-11] design | Policy engine requirements document

**Pages created:**
- `docs/design/policy-engine-requirements.md` — functional and non-functional requirements for the PolicyEngine. 9 functional requirement groups (definition, context, stages, fail-closed, decisions, enforcement points, grant integration, enforcement modes, protocol), 4 NFRs, 6 design decisions (P1-P6).

**Pages updated:**
- `docs/index.md` — added requirements doc entry

**Key decisions:**
- P1: CEL as default (CNCF-aligned, embeddable, 1-3ms in Python), OPA/Cedar as contrib adapters
- P2: First-match-wins by priority, per-stage evaluation
- P3: Fail-closed on CEL errors (non-configurable security invariant)
- P4: Advisory/soft/hard enforcement modes per-policy (gradual rollout pattern)
- P5: No matching rule → ALLOW (grant enforcement policy provides the default deny)
- P6: Grants are data on AgentRecord; policies read them, don't execute them

**Prior research leveraged:**
- /Users/jeryn/workspace/projects/policy-engines-ai-governance/ — 12 articles covering OPA, Cedar, CEL, SpiceDB, AI governance patterns, architecture patterns, decision matrix
- Key insight: CEL is 1-3ms in cel-python (acceptable), non-Turing-complete (safe), CNCF-aligned (enterprise)
- Key insight: Layered evaluation pattern validates CEL-first → OPA-later architecture
- Key insight: Advisory → soft → hard enforcement modes are essential for production policy deployment

## [2026-06-11] rfc | Seed RFC for multi-dimensional evaluation

**Pages created:**
- `docs/rfcs/002-multi-dimensional-evaluation.md` — seed RFC capturing the insight that scalar evaluation of non-deterministic systems is a category error. Current LLM evals collapse high-dimensional outputs to single scores, losing dimensional detail, confidence bounds, and context. Proposes distributional, multi-dimensional evaluation outputs with per-dimension uncertainty and explicit caveats. Marked as post-M4 investigation — M2 TrustScorer ships as simple scalar.

**Pages updated:**
- `docs/vision/roadmap.md` — added "Future Investigation: Multi-Dimensional Evaluation" section referencing RFC-002
- `docs/index.md` — added RFC-002 entry

## [2026-06-11] design | Credential provider requirements and design

**Sources researched:**
- Civitas credential infrastructure: SecretsProvider protocol, per-agent credentials: block, get_credential(), model_for(), secret.access audit events, ${VAR_NAME} substitution
- HashiCorp Vault: AppRole auth, KV v2 API, lease-based tokens, dynamic secrets
- AWS Secrets Manager: IAM-based access, GetSecretValue API, Lambda rotation
- Infisical: machine identities, universal auth, periodic tokens, path-based scoping
- Doppler: service accounts, config tokens, environment-based scoping
- SOPS: encrypted secrets in git (not applicable as a runtime provider)
- Agent frameworks (LangChain, CrewAI, AutoGen): all use env vars with ZERO credential isolation

**Pages created:**
- `docs/design/credential-provider-requirements.md` — 6 FRs, 3 NFRs, 5 design decisions (C1-C5). Key insight: credentials are resources in the grant model (`credential:{name}`), unified with tool and LLM authorization.
- `docs/design/credential-provider.md` — Protocol definition, EnvCredentialProvider and FileCredentialProvider defaults, Vault/AWS contrib sketches, topology YAML integration, audit event shape, Civitas integration points.

**Pages updated:**
- `docs/index.md` — added both entries to Design table

**Key decisions:**
- C1: Credentials are resources in the grant model (`credential:{name}`) — unified authorization
- C2: Protocol with env/file defaults, Vault/AWS/Infisical as contrib adapters
- C3: Wrap Civitas's existing `agent._credentials` — zero changes to Civitas core
- C4: Transparent token renewal in remote backends
- C5: Enriched `credential.access` audit events (grant context + trust tier)
- C6: Credential values NEVER appear in logs or audit events

## [2026-06-11] design | Approval service requirements and design

**Sources leveraged:**
- Civitas HITL pattern (examples/patterns/human_in_the_loop.py) — message-based approval with self.state persistence
- Civitas-Presidium boundary doc — integration point #8 (durable suspension)
- Policy engine design — REQUIRE_APPROVAL decision type with approvers list
- Presidium HTTP gateway design sketch — /api/v1/approvals endpoints
- EU AI Act Art. 14 — human oversight mechanisms required for high-risk AI
- Singapore 2026 agentic AI framework — escalation paths for out-of-scope actions
- Policy engines research — approval workflows in OPA, Cedar, Cerbos

**Pages created:**
- `docs/design/approval-service-requirements.md` — 7 FRs, 3 NFRs, 5 design decisions (A1-A5). Key: async waiting with fail-closed timeout, approval records as M4 decision journal training data.
- `docs/design/approval-service.md` — Protocol definition, CallbackApprovalProvider default, Slack/Temporal/Webhook contrib sketches, PEP integration code, audit event shapes, topology YAML config, connection to autonomy progression.

**Pages updated:**
- `docs/index.md` — added both entries

**Key decisions:**
- A1: Async waiting — PEP awaits with timeout, agent continues processing other messages
- A2: Fail-closed on timeout — auto-deny after configurable timeout (default 30 min)
- A3: CallbackApprovalProvider as default — programmatic callbacks for dev/test
- A4: Approval records persisted — training data for M4 autonomy progression
- A5: Rich context sent to approvers — trust tier, recent violations, last approval, action details

## [2026-06-11] design | Audit enricher requirements and design

**Sources leveraged:**
- Civitas audit infrastructure: AuditEvent TypedDict, AuditSink protocol, 4 built-in sinks (NullSink, JsonlFileSink, SyslogSink, OtlpSink), 5 emission points (MessageBus.route, AgentProcess.get_credential, MCPTool, sandbox)
- Civitas-Presidium boundary doc integration point #4 (AuditSink — Civitas emits, Presidium enriches)
- Presidium governance events defined across all design docs: policy.evaluated, credential.access, approval.requested, approval.decided, agent.registered, trust.updated, grant.added/removed
- EU AI Act Art. 12 (record-keeping), ISO 42001 Annex A.8 (transparency)

**Pages created:**
- `docs/design/audit-enricher-requirements.md` — 5 FRs, 3 NFRs, 5 design decisions (E1-E5). Key: middleware pattern wrapping downstream AuditSink, fail-open forwarding, namespaced enrichment under details.governance.
- `docs/design/audit-enricher.md` — Protocol definition, InProcessAuditEnricher with cached registry lookups, complete governance event type table (14 types total: 5 Civitas + 9 Presidium), topology YAML integration, Civitas integration points.

**Pages updated:**
- `docs/index.md` — added both entries

**Key decisions:**
- E1: Middleware pattern — wraps downstream AuditSink, no Civitas changes
- E2: Fail-open forwarding — enrichment errors don't drop events
- E3: Namespaced enrichment — governance data under details.governance key
- E4: Cached registry lookups — 5-second TTL to handle high-throughput buses
- E5: Unified pipeline — Civitas + Presidium events in the same audit stream

## [2026-06-11] design | Topology integration requirements and design

**Sources leveraged:**
- Civitas Runtime.from_config() source code — YAML loading, _KNOWN_CONFIG_KEYS validation, plugin loading, ComponentSet wiring
- Civitas plugin loader — entrypoint groups, built-in mappings, lazy imports
- Civitas Runtime.__init__() — accepts components: ComponentSet for pre-built injection
- Civitas-Presidium boundary doc — integration points for ModelProvider, ToolProvider, AuditSink

**Pages created:**
- `docs/design/topology-integration-requirements.md` — 6 FRs, 3 NFRs, 5 design decisions (T1-T5). Key: single YAML file, GovernedRuntime wrapper, 2 minimal Civitas changes.
- `docs/design/topology-integration.md` — GovernedRuntime class design, startup sequence, full YAML example, component wrapping strategy, Civitas diff (2 changes).

**Pages updated:**
- `docs/index.md` — added both entries

**Key decisions:**
- T1: Single YAML file with presidium: top-level key
- T2: GovernedRuntime.from_config() wraps Runtime.from_config_dict() (delegation, not inheritance)
- T3: 2 minimal Civitas changes — add "presidium" to known keys + add from_config_dict() classmethod
- T4: Component wrapping happens before Runtime.start() — no governance gap
- T5: Missing presidium: block = no governance (opt-in, not mandatory)

**Civitas changes required:**
1. Add `"presidium"` to `_KNOWN_CONFIG_KEYS` in `civitas/runtime.py` (1 line)
2. Refactor `from_config()` to extract `from_config_dict()` classmethod (small, non-breaking)

## [2026-06-12] review | Full M2 design review and fixes

**Review conducted by:** Oracle (architectural review) + explore agent (mechanical consistency check)

**Review scope:** All 12 M2 design and requirements docs, checked for internal consistency, missing requirements, design principle violations, M3/M4 compatibility, security, and operational concerns.

**Findings:** 12 issues, 7 risks, 7 suggestions identified. 9 issues fixed, 3 deferred, 5 risks documented.

**Issues fixed:**
- I-1: `packages.md` Protocol signatures rewritten to match canonical design docs (all 6 component code examples updated)
- I-2: `trust_domain` added to registry YAML schema (FR-1.10) and GovernedRuntime config (default: "local")
- I-4: Audit event `agent` field standardized — short name for Civitas compat, URI in `details.governance.agent_id`
- I-6: Trust decay specified as lazy-on-read with materialization-on-write (avoids background timers, deterministic within evaluation)
- I-7: `trust_events` SQL table added to registry persistence schema — M4 training data for LearningTrustScorer
- I-8: AuditEnricher re-enrichment guard added — events with existing `governance` key forwarded as-is (FR-1.5)
- I-10: Multi-stage policy rules enabled — `stage` accepts `EvaluationStage | list[EvaluationStage]` (FR-3.6)
- I-12: `pre_message` deferred to M3 — requires Civitas MessageBus hook outside M2 scope. M2 has 3 stages (pre_tool, pre_llm, registration)
- status.changed: Added to audit-enricher event type table (15 total: 5 Civitas + 10 Presidium)

**Additional fixes from suggestions:**
- S-3: `Grant.id: str | None` added for stable removal (replaces index-based `remove_grant`)
- R-4: Default approval timeout changed from 30 minutes to 5 minutes
- R-6: Enforcement mode interaction with first-match-wins clarified with priority ordering guidance
- I-9: Grant pre-filtering documented as PolicyEngine Protocol contract

**Previously deferred, now resolved:**
- I-3: AuditEvent pinned as TypedDict with documented access pattern (dict-style) — FR-2.5 added to audit-enricher-requirements, type contract section added to audit-enricher.md
- I-5: Concurrent grant modification — snapshot semantics specified on `lookup()`. Returns immutable snapshot with revision number. FR-6.5 added to agent-registry-requirements. Protocol docstring updated in agent-registry.md.
- I-11: `PolicyResult.policy_name` changed from `str` to `str | None = None`. No-match returns `None` instead of empty string. FR-5.1 updated in policy-engine-requirements.

**Risks tracked:**
- R-1: 10-20ms governance overhead per call — benchmark early
- R-2: SQLite serializes writers — document library mode as single-process
- R-3: AuditEnricher cache shows stale trust for 5s — acceptable for M2
- R-5: InProcessAuth trusts the runtime — document trust boundary

**Pages updated:** agent-registry.md, agent-registry-requirements.md, policy-engine.md, policy-engine-requirements.md, audit-enricher.md, audit-enricher-requirements.md, approval-service.md, approval-service-requirements.md, topology-integration.md, topology-integration-requirements.md, architecture/packages.md (11 files total)

**All 12 issues resolved. 0 deferred. M2 design is ready for implementation.**

## [2026-06-12] plan | M2 implementation plan

**Pages created:**
- `docs/design/implementation-plan.md` — 6-phase build plan with dependency graph, verification strategy per phase, package/module layout, risk mitigation, phase gates, testing strategy, timeline (~11 days solo, ~7 days with 2 devs).

**Pages updated:**
- `docs/index.md` — added implementation plan entry
- `docs/vision/roadmap.md` — M1 items marked complete (design docs, research, review), M2 updated with design-complete status, M3 updated with deferred items (pre_message, WebhookApprovalProvider, policy hot-reload, concurrent grants)

**Phase summary:**
- Phase 1 (0.5d): Data model + CEL risk spike
- Phase 2 (2d): Core abstractions — TrustScorer, PolicyEngine Protocol, CredentialProvider, Civitas changes (4-wide parallel)
- Phase 3 (2.5d): Primary implementations — InMemoryRegistry, CelPolicyEngine, CallbackApprovalProvider (3-wide parallel)
- Phase 4 (1d): AuditEnricher
- Phase 5 (2d): GovernedModelProvider + GovernedToolProvider (2-wide parallel)
- Phase 6 (3d): GovernedRuntime + SqliteRegistry + integration tests + public API

**Key decisions:**
- CelPolicyEngine is highest risk — de-risked with Phase 1 spike before Protocol shapes are finalized
- SqliteRegistry built LAST — InMemoryRegistry proves the Protocol, SQLite gets parity testing for free via parametrized test suite
- Phase gates enforce Protocol review before consumers are built (Phase 2→3 gate)

---

## [2026-06-12] impl | M2 Phases 1-6 implementation complete

**Implementation delivered:**
All 6 phases of the M2 implementation plan completed. 18 source modules, 234 tests, 95% coverage. mypy strict clean, ruff clean.

**Modules created (packages/presidium/src/presidium/):**
- `model.py` — 8 enums, 8 dataclasses (Phase 1)
- `errors.py` — PresidiumError hierarchy, 9 exception classes (Phase 1)
- `trust.py` — TrustScorer Protocol + LinearTrustScore (Phase 2)
- `policy/_base.py` — PolicyEngine Protocol (Phase 2)
- `credentials.py` — CredentialProvider Protocol + EnvCredentialProvider + FileCredentialProvider (Phase 2)
- `registry/_base.py` — AgentRegistry Protocol (Phase 3)
- `registry/memory.py` — InMemoryRegistry (Phase 3)
- `policy/cel.py` — CelPolicyEngine with cel-python (Phase 3)
- `approval.py` — ApprovalService Protocol + CallbackApprovalProvider (Phase 3)
- `audit.py` — AuditEnricher Protocol + InProcessAuditEnricher (Phase 4)
- `providers/model.py` — GovernedModelProvider (Phase 5)
- `providers/tool.py` — GovernedToolProvider (Phase 5)
- `registry/sqlite.py` — SqliteRegistry with aiosqlite (Phase 6)
- `runtime.py` — GovernedRuntime programmatic constructor (Phase 6)

**Test coverage highlights:**
- Registry tests parametrized across InMemoryRegistry and SqliteRegistry (one suite, two backends)
- CEL spike validated cel-python: json_to_cel, .exists() macros, CELParseError, CELEvalError
- 100 concurrent writer stress test for both registry backends
- Trust decay math validated with table-driven golden tests

**Pages updated:**
- `docs/vision/roadmap.md` — M2 status updated to implementation complete, remaining items listed
- `docs/design/implementation-plan.md` — status updated
- `docs/index.md` — status and last-updated refreshed

**Remaining for M2 completion:**
- `GovernedRuntime.from_config()` — blocked on Civitas `Runtime.from_config_dict()` extraction
- 2 Civitas changes: add `"presidium"` to `_KNOWN_CONFIG_KEYS`, extract `from_config_dict()` classmethod
- Integration tests with real Civitas Runtime
- Getting started guide

---

## [2026-06-14] design | M3 architecture revision — AgentGateway, post-hooks, MCP governance

**Research conducted:**
- AgentGateway (Linux Foundation, Agentic AI Foundation): Rust-based gateway for LLM + MCP + A2A, native CEL policies, OpenTelemetry, 3.3k stars
- MCP governance landscape: 10+ projects surveyed (mcp-zero, mcp-guardian, mcpx, mcp-proxy, mcp-gov, secure-mcp-gateway, etc.)
- Post-execution patterns: NeMo Guardrails output rails, Guardrails AI validators, MCP gateway response scanning

**Architecture decisions:**
1. **Replace LiteLLM with AgentGateway** — AgentGateway is agent-centric (LLM + MCP + A2A) vs LiteLLM's LLM-centric focus. Native CEL policy engine aligns with Presidium. Linux Foundation backing.
2. **Responsibility split defined** — Presidium owns authorization (grants, trust, approval). AgentGateway owns operations (routing, rate limiting, cost tracking). Clear boundary.
3. **Post-execution stages** — `POST_TOOL` and `POST_LLM` added to M3 scope. Same CEL engine for governance checks (PII detection, result filtering). Content validation (hallucination, toxicity) is a separate concern via NeMo/Guardrails AI contrib adapters.
4. **MCP governance patterns adopted** — default-deny via grants, tool fingerprinting (hash-based), output PII masking (POST_TOOL + regex/Presidio detection), credential redaction, shadow/audit mode.

**Pages updated:**
- `docs/vision/roadmap.md` — M3 scope revised: LiteLLM → AgentGateway, post-execution stages added
- `docs/architecture/packages.md` — LiteLLM references replaced with AgentGateway
- `docs/design/policy-engine.md` — POST_TOOL/POST_LLM stages added, P7 decision updated, open question resolved
- `docs/design/llm-gateway.md` — responsibility split between Presidium (authorization) and AgentGateway (operations)
- `docs/design/mcp-gateway.md` — post-execution output validation, PII masking, MCP landscape research
- `AGENTS.md` — LiteLLM → AgentGateway in package structure, adapters, dependency rules, glossary
- `docs/index.md` — roadmap summary updated

## [2026-06-16] implementation | M3 complete — enterprise trust, MCP governance, service mode

**M3 implementation completed in full.** 442 tests passing (336 core + 106 contrib), 95%+ coverage, mypy strict, ruff clean.

**Implemented (presidium core):**
- Enterprise trust requirements FR-E.1–E.6: spec pinning, override attribution, performance budget, zero-downtime migration, determinism contract, OpenTelemetry instrumentation
- `presidium.scoring` library validated as reusable across trust consumers
- `WindowedTrustScorer` with cold-start blending, controllability filter, spec introspection
- `GovernedMessageBus` — PRE_MESSAGE policy enforcement point
- Policy hot-reload via `GovernedRuntime.reload_policies()` (atomic swap)
- New errors: `SpecMismatchError`, `MissingAttributionError`, `TrustScoringError`

**Implemented (presidium-contrib):**
- `LearningTrustScorer` refactored to use `presidium.scoring` library
- MCP governance reference impl: `PoisoningDetector`, `redact_dict`, `PIIDetector`
- Service mode GenServer wrappers: `PolicyEvaluatorServer`, `RegistryServer`

**RFC-003 drafted:** Agent Value Chain — from registry to business value. Five SVG diagrams, 15+ industry/academic sources cited.

**Pages updated:**
- `AGENTS.md` — package map refreshed with all M3 modules
- `README.md` — status updated, LiteLLM → AgentGateway, packages table refreshed
- `docs/index.md` — status updated, LiteLLM → AgentGateway
- `docs/vision/roadmap.md` — M3 checkboxes marked complete, timeline updated
- `docs/architecture/packages.md` — module layout rewritten to match actual code
- `docs/design/credential-provider.md` — Vault → OpenBao terminology
- `docs/rfcs/001-presidium-scope.md` — removed LiteLLM from Civitas plugin list
- `CHANGELOG.md` — M3 features documented under Unreleased
- `HANDOFF.md` — verified 100% accurate

---

## [2026-06-30] lint | Corrected competitor prior-art overclaims

**Issue:** Several positioning surfaces claimed no prior art / no existing product exists for MCP governance, trust scoring, and agent registries. This contradicted the competitive research already in this wiki (Microsoft AGT ships an MCP Security Gateway and a 0–1000 trust model; Google Gemini ships an agent registry) and the design docs referencing the AGT-style scorer.

**Correction:** The accurate rationale for shipping reference implementations is that prior art exists but is coupled to its host platform and not available as a standalone, swappable library to wrap — not that the space is empty.

**Pages updated:**
- `README.md` — "Where Presidium Builds vs. Wraps" table (registry, MCP governance, trust scoring rows) + section intro
- `AGENTS.md` — reference-implementations table + heading
- `docs/architecture/packages.md` — component map note, overview, and the registry / trust / MCP "reference impl" rationale lines

**Superseded:** The 2026-04-30 entry's "Where nothing exists (Agent Registry with grants+trust, MCP governance, Trust scoring)" framing is corrected by this entry — prior art exists; it simply isn't packaged as a reusable library.

---

## [2026-07-07] lint | Fixed stale Cedar-primary policy-engine claim in RFC-001

**Issue:** `docs/rfcs/001-presidium-scope.md` still stated "Cedar primary, OPA supported" for the
policy engine (in the Scope summary, the Presidium-Provides section, an AAA table row, and as an
open unresolved question). This predates the actual M2 decision to ship CEL as the primary
(embedded-library) policy engine — `docs/vision/roadmap.md` and `AGENTS.md` were already correct
("CEL default", "CEL — the default policy engine in presidium"); RFC-001 was never updated to match
when the Cedar→CEL pivot happened before M2 shipped.

**Correction:** RFC-001 now states CEL is primary (shipped, `presidium/policy/cel.py`), OPA is
supported via `presidium-contrib[opa]`, and Cedar is deferred to a future adapter (matching
`docs/vision/roadmap.md`'s existing "Deferred adapters: CedarPolicyEngine" line) — not a
primary-engine candidate. The open question "Cedar vs. OPA as primary policy engine" is resolved
and moved out of Open Questions into the Decision section with rationale (CEL's zero-ops,
embeddable nature fit Presidium's library-mode-by-default principle for a first implementation).

**Pages updated:**
- `docs/rfcs/001-presidium-scope.md` — header revision note, Scope summary, Presidium-Provides
  bullet, AAA authorization-decisions table row, Open Questions → Decision resolution
- `docs/index.md` — last-updated date, RFC-001 status note (this entry)

---

## [2026-07-07] design | Pluggable LLM/Tools gateway backends + agents-as-tools scoping

**Discussion:** Human wants Presidium's gateway integration to support multiple LLM/MCP gateway
products, not be hardcoded to AgentGateway — preferring AgentGateway as the reference but wanting
real optionality (explicitly named preference for AgentGateway; explicitly does not want the second
backend choice frozen). Also wants LLM Gateway and Tools/MCP Gateway kept as two logically separate
components even though AgentGateway ships both in one product, specifically to keep the door open
for "agents as tools" (A2A delegation through the same governed path as MCP tools) — outbound only
for now, inbound (civitas agents exposed as A2A-callable) explicitly scoped as a non-goal/fast-follow
rather than silently dropped.

**Research done (this session):** Evidence-based comparison of 6 LLM/AI gateway candidates
(LiteLLM Proxy, Kong AI Gateway, Portkey, Cloudflare AI Gateway, Helicone, TrueFoundry) across
GitHub adoption, PyPI downloads, named customers, funding, self-hostability, Python-native fit, and
license. LiteLLM Proxy is the strongest candidate for a second fully-built adapter (52.8k GitHub
stars, MIT license, self-hostable, Python-native, named production users), with real caveats
weighed (a recent CVE history on its auth path; heavier operational footprint than AgentGateway's
single binary; the ~471M/30-day PyPI download figure is likely inflated by transitive-dependency
installs, not read as a literal usage signal). Per explicit instruction, **this pick is a lean, not
a lock-in** — documented as such everywhere it's mentioned.

**Design decisions:**
- New `LLMGatewayBackend` Protocol (`presidium/providers/gateway.py`) — `GovernedModelProvider`'s
  operations dependency, extracted from its previous AgentGateway-only hardcoding.
- New `ToolsGatewayBackend` Protocol (same file) — `GovernedToolProvider`'s operations dependency.
  `call_tool()` is deliberately uniform for an MCP tool and an A2A-delegated agent (the "agents as
  tools" scoping), outbound only.
- AgentGateway is the reference/fully-built adapter for both protocols (though its `ToolsGatewayBackend`
  side needs `list_tools`/`call_tool` added to its existing `client.py` — a real implementation gap,
  not a design gap, tracked as a GH issue).
- LiteLLM Proxy is the leading (not frozen) second `LLMGatewayBackend` candidate. Kong, Portkey,
  Cloudflare AI Gateway, Helicone, TrueFoundry get stub-only adapters (interface-conformant,
  `NotImplementedError`) to reserve the extras and prove the Protocol generalizes.
- No second `ToolsGatewayBackend` candidate — documented as a real, current gap (nothing in the
  market research does MCP+A2A with Presidium's self-hostable/Python-native bar), not filled in
  arbitrarily.

**Pages updated:**
- `docs/design/llm-gateway.md` — pluggable backend Protocol, adapter comparison table, non-goals,
  open questions
- `docs/design/mcp-gateway.md` — pluggable backend Protocol, agents-as-tools design, inbound A2A
  non-goal, MCP Governance Landscape note, open questions
- `docs/architecture/packages.md` — package tree, Component Map table, LLM/MCP Gateway code
  samples, presidium-contrib adapter list, overview paragraph
- `docs/index.md` — LLM Gateway / MCP Gateway / Package Map row descriptions

**Not done in this pass (deferred to implementation / GH issues):**
- Actually writing `presidium/providers/gateway.py`, the `litellm/` adapter, or the stub adapters —
  this pass is docs-only, per explicit instruction to sort docs before issues/code.
- Adding `list_tools`/`call_tool` to `agentgateway/client.py` — same reason.
- Resolving the grant shape for agent-targets (`agent:<name>:invoke`?) — flagged as an open question
  in `mcp-gateway.md`, not resolved here.

---

## [2026-08-22] design | New milestone M7: Presidium Server (self-hostable network governance service)

**Trigger:** A cross-project deep dive (from the private `civitas-io/context` wiki) surfaced a
real, concrete gap: `civitas-io/fabrica`'s `PresidiumClient` Protocol (`check_grant()`) is fully
specified and implementation-ready, but has nothing real to talk to. Presidium's governance
components are reachable in-process (as a library) or via Civitas's own actor transport (Service
Mode's `PolicyEvaluatorServer`/`RegistryServer` GenServers, callable only by other Civitas
agents) — neither is reachable by an external, non-Civitas system.

**Decision:** Added **M7: Presidium Server** to `docs/vision/roadmap.md`, after M6. Scoped as the
OSS, self-hostable building block distinct from M6's commercial "Presidium Cloud" — M6 would
eventually run as a managed, multi-tenant deployment of what M7 builds, not the reverse.
Deliberately scoped as "build the server RFC-001's AAA architecture already describes" plus "add
a REST transport skin around `GovernedRuntime`'s existing composition," not a new architecture
decision or a rewrite of governance logic.

**Concrete, real requirements captured** (see the milestone itself for the full list):
must satisfy `civitas-io/fabrica`'s `PresidiumClient.check_grant()` contract exactly (confirmed
directly against `civitas-io/fabrica/docs/contracts/managers.md` — synchronous REST, `agent_id` +
`action` + `scope` in, `GrantResult` out); mTLS via the existing SPIFFE-compatible identity model,
not bearer tokens; must close the `service/policy.py`/`service/registry.py` 0%-coverage gap before
building a network-facing layer on top of them; a real package-shape decision (`presidium-server`
vs. `presidium-contrib[server]`) explicitly deferred to an ADR rather than picked silently here.

**Two small, real doc-drift fixes made in the same pass, found while grounding this milestone:**
- `docs/architecture/overview.md` still said "Cedar policy engine" in one line, contradicting the
  same file's own later "CEL as Default Policy Language" section — same class of staleness
  already fixed elsewhere (RFC-001, 2026-07-07) but missed in this file. Fixed to say CEL.
- `docs/design/agent-registry.md` describes a `presidium-contrib[spiffe]` extra ("M3+ upgrade
  path") that does not exist anywhere in the real codebase (`pyproject.toml`, `AGENTS.md`'s own
  extras table). Not fixed in this pass — instead pointed to explicitly as real, in-scope work
  for M7 itself (mTLS needs exactly this), so the gap is now tracked rather than silently
  left dangling or papered over with a doc correction that still leaves no real code behind it.

**Pages updated:**
- `docs/vision/roadmap.md` — new M7 section, Timeline table row
- `docs/architecture/overview.md` — Cedar → CEL fix
- `docs/log.md` — this entry

---

## [2026-08-22] finding | Ed25519 identity binding was never actually wired up (M2 documented as done, real code skips it)

**Trigger:** A follow-up question during the M7 scoping work ("is SPIFFE/identity implementation
complete?") prompted checking the real construction path, not just the design docs.

**Finding:** `docs/design/agent-registry.md` states "each agent's identity is bound to its
Ed25519 keypair... Civitas already provisions Ed25519 keypairs for message signing (M4.2a);
Presidium reuses them for identity" as M2 behavior. The real code does not do this.
`GovernedRuntime.start()` (`presidium/runtime.py`) constructs every `AgentRecord` with
`public_key=""` — a hardcoded empty string. `AgentRegistry`'s Protocol has no
`verify_signature()` or equivalent method. `public_key` is a plain passthrough field, persisted
by `SqliteRegistry`/`PostgresAgentRegistry`'s schemas, but nothing in the codebase ever
populates it with a real key or checks it against anything. Civitas's own
`civitas.security.identity.AgentIdentity` (with a real `public_key_b64()`) already exists and is
exactly what the design doc describes reusing — it is simply never called from Presidium.

**Impact:** Presidium's own agent identity has no real cryptographic verification today, despite
M2 (marked Complete) documenting this as delivered. The `presidium://` URI scheme is real; the
"binding" half of "cryptographic binding" is not.

**Not retroactively unmarking M2** — that would rewrite a shipped milestone's history. Instead,
added two explicit, separately-tracked checklist items to the new M7 milestone
(`docs/vision/roadmap.md`): (1) wire up the real Ed25519 binding via
`civitas.security.identity.AgentIdentity`, named as a prerequisite for M7's mTLS meaning
anything, not an optional nice-to-have; (2) build the still-undocumented-as-missing
`presidium-contrib[spiffe]` extra (real SPIRE-issued X.509-SVIDs) — previously only mentioned as
a parenthetical, now its own first-class item.

**Pages updated:**
- `docs/vision/roadmap.md` — M7 section, two explicit checklist items replacing one bundled bullet
- `docs/log.md` — this entry

---

## [2026-08-22] design | New milestone M8: Performance Research — Rust vs. Python at the governance hot path

**Trigger:** A direct question drawing on real, external precedent already cited in this repo's
own `docs/design/llm-gateway.md` — AgentGateway (Rust) scales structurally differently than
LiteLLM Proxy (pure Python), which is reportedly moving toward a Rust rewrite for that reason.
Presidium's own policy-evaluation hot path has the identical shape: pure Python, synchronous,
in the critical path of every governed action.

**Real benchmarks run before writing anything down, not assumed:**
- `CelPolicyEngine.evaluate()` (confirmed pure-Python `cel-python`/`celpy`, a `lark`-based
  tree-walking interpreter — no Rust/C core): ~88μs/call, ~11,400 evals/sec on one core with 20
  loaded rules, first-match-wins.
- `InMemoryRegistry.lookup()`: ~9μs/call, ~112,000 lookups/sec on one core — not the bottleneck.
- The real constraint is the GIL, not the per-call cost in isolation: this ceiling doesn't rise
  with more cores within one process, only via horizontal replicas — the same structural shape
  as AgentGateway's advantage over LiteLLM.

**Decision:** Added M8 to `docs/vision/roadmap.md`, sequenced after M7 (this only becomes a real,
load-bearing concern once Presidium is an externally-callable, multi-tenant service — library-mode
usage today pays this cost once per call inside an agent's own loop, negligible next to LLM
latencies). Scoped explicitly as a **research milestone, not a rewrite commitment** — four options
listed (horizontal scaling only, free-threaded CPython/PEP 703, a Rust-backed CEL evaluator behind
the existing `PolicyEngine` Protocol, or a fuller Rust rewrite of the M7 network layer
specifically), deliverable is a design doc with real numbers and a recommendation, not code. Matches
this project's own "ship the default, revisit only with evidence" discipline (same discipline that
shipped `fabrica`'s retriever as pure Python v1 without pre-optimizing in Rust).

**Pages updated:**
- `docs/vision/roadmap.md` — new M8 section, Timeline table row
- `docs/log.md` — this entry

---

## [2026-08-22] design | New "Implementation Priority (P0/P1/P2)" section in the roadmap

**Trigger:** A direct request, as part of a wider cross-project completion push covering
`python-civitas`, `presidium`, and `fabrica` together, to turn this session's accumulated real
findings into an explicit, actionable priority order rather than leaving them scattered across
individual milestone checklist items and chat history.

**Decision:** Added a new "Implementation Priority (P0/P1/P2)" section to
`docs/vision/roadmap.md`, positioned right after Philosophy and before M1 — deliberately
orthogonal to the M-numbered milestones (which remain the source of truth for *scope*; this
section is the source of truth for *sequencing and urgency*). Tagged M4/M5/M6/M7/M8 with their
priority level inline. Reordered/tagged M7's own requirement list so its two P0 sub-items (the
Ed25519 binding fix, the `service/*` coverage gap) read first, ahead of its P1 sub-items
(`presidium-contrib[spiffe]`, rate limiting).

**One real correction made while writing this down, not just a restatement**: an earlier framing
(in conversation, not previously committed to any doc) said the missing
`LLMGatewayBackend`/`ToolsGatewayBackend` wiring in `GovernedModelProvider`/`GovernedToolProvider`
blocks Fabrica's `PresidiumClient`. On closer reading of `civitas-io/fabrica`'s own contract, this
is not accurate — `PresidiumClient.check_grant()` only needs a decision; Fabrica executes tool
calls itself in its own sandbox. The real, correct reason this gap is still P0: it blocks
`GovernedModelProvider`/`GovernedToolProvider` from being usable as a drop-in Civitas
`ModelProvider`/`ToolProvider`, which is their own stated purpose per RFC-001 and the design docs'
own code samples — a different but equally real completeness gap. Recorded as its own explicit,
previously-untracked item (not folded into any single M-section, since it's independent of M7's
network-layer scope even though both draw on the same 2026-07-07 design work).

**Also added, not previously tracked anywhere**: pinning `civitas` to a real PyPI release
(`civitas>=0.11.0`) instead of `git`/`branch = "main"` in the workspace root `pyproject.toml` —
found while compiling this list, has no natural home in any existing M-section, tracked directly
in the new Priority section.

**Pages updated:**
- `docs/vision/roadmap.md` — new Priority section, milestone priority tags, M7 requirement
  reordering/tagging
- `docs/log.md` — this entry

---

## [2026-08-22] research | Comparison against Microsoft's Agent Governance Toolkit (AGT)

**Trigger:** A direct request to review `microsoft/agent-governance-toolkit` (v4.1.0, MIT,
public preview) and identify conceptual gaps or ideas worth adopting.

**Scale context, stated honestly:** AGT is substantially more mature than Presidium today — 5
language SDKs, 9 packages/5 PyPI distributions, 10 formal RFC 2119 specs backed by 992
conformance tests, 29 ADRs, real compliance mappings (OWASP Agentic Top 10, NIST AI RMF, EU AI
Act, SOC 2), and a Rust-core policy engine (Agent Control Specification / ACS) with a Python SDK
built via maturin.

**Two real, concrete security gaps found in Presidium via this comparison, now tracked as P1
roadmap items** (see the two new bullets under "Implementation Priority" → P1):

1. **No trust ceiling propagation.** AGT's `AGENTMESH-IDENTITY-TRUST-1.0` spec requires a
   `trust_ceiling` on every agent, enforced at creation, on every score update, and across
   delegation chains (`child ceiling <= parent ceiling`) — specifically to prevent "trust
   washing" (an attacker repeatedly spawning fresh identities to reset a degraded trust score).
   Presidium has no equivalent: cold-start values are independent of a parent's own trust.
2. **No enforcement of monotonic capability narrowing on delegation/spawn.** AGT requires every
   delegated capability set to be a strict subset of the delegator's own, hash-chained for
   tamper-evidence, with a hard depth limit. Presidium's `parent_agent_id` records lineage but
   enforces nothing about what a child is granted — a child can currently end up with *more*
   grants than its parent.

**Real architectural ideas noted, not committed to any specific implementation yet:**
- ACS's `transform` verdict type (a policy decision can sanitize/redact as part of one unified
  verdict, vs. Presidium's separate `redact_dict()`/`PIIDetector` utilities layered on top).
- AGT's MCP Security Gateway is far more built out than Presidium's `mcp_gateway`: message
  signing with replay protection, session tokens with TTL, sliding-window rate limiting (already
  a P1 M7 item here independently), per-server TLS/auth enforcement, CVE feed integration (OSV
  API), cross-server confused-deputy detection. Added as real candidates to the MCP-governance
  P1 item, not committed wholesale.
- Formal RFC 2119 specs + dedicated conformance suites as a distinct discipline from test
  coverage % — worth considering as Presidium's own `docs/design/*.md` mature further.

**Real, honest findings that don't require Presidium action, or point elsewhere in the org:**
- AGT's own "Known Limitations" doc names a composability gap (two individually-permitted
  actions forming a data-exfiltration path) that Presidium's per-action CEL evaluation shares
  today, undocumented as such here.
- AGT's "Knowledge Governance Gap" (provenance/freshness/classification of retrieved RAG
  context) and a cited cross-session persistent-memory attack chain
  (Dai et al., arXiv 2605.06158, 80-95% ASR) are directly relevant to `civitas-io/fabrica`'s
  `Retriever`/`MemoryManager`, not Presidium — flagged for that project's own review, not acted
  on here.
- AGT's own published <0.1ms Rust policy-eval number is close to Presidium's own measured 88us
  pure-Python number at comparable rule counts (see M8's own benchmarks) — a useful data point
  that tempers, without eliminating, the case for M8's Rust research.
- Where Presidium's own ecosystem may already be ahead, not behind: `civitas-io/fabrica`'s real,
  hardware-validated OS-level execution isolation (AGT recommends per-agent containers as an
  *external* mitigation, since AGT itself only governs at the application-middleware layer);
  `civitas-io/tessera`'s agent-blind credential model is arguably stronger than AGT's own
  admitted "Credential Persistence Gap."

**Full comparison recorded in `civitas-io/context`'s `competitive-analysis.md`.**

**Pages updated:**
- `docs/vision/roadmap.md` — two new P1 items (trust ceiling, capability narrowing), MCP
  governance item enriched with real candidates
- `docs/log.md` — this entry

---

## [2026-08-22] finding | M7 should reuse civitas.gateway.HTTPGateway, not build a new server

**Trigger:** A cross-project completion review of `python-civitas` itself (part of the same
effort covering `presidium` and `fabrica`) found that `python-civitas` already ships a mature,
well-tested, production-grade HTTP/gRPC/HTTP3 gateway (`civitas.gateway`) with real mTLS
(`gateway/mtls.py`, 98% covered) and real JWT bearer auth (`gateway/jwt_auth.py`, 100% covered) —
confirmed by reading the real source and its own examples (`examples/http_gateway.py`,
`examples/gateway_auth.py`), not assumed from the package name.

**Finding:** `HTTPGateway` is transport-agnostic and fully declarative — a route is just
`{"method": "POST", "path": "/v1/...", "agent": "<name>", "mode": "call"}`, dispatched onto the
Civitas bus to *any* named agent via `GatewayDispatcher`. Since M7's own
`PolicyEvaluatorServer`/`RegistryServer` are already real `AgentProcess`/`GenServer` subclasses
(shipped in M3), most of M7's planned "REST endpoints" and "mTLS" work could be satisfied by
registering these agents behind an `HTTPGateway` with a routes/`GatewayConfig` manifest, instead
of building a new REST+mTLS server framework from scratch.

**Decision:** Added this as a major finding directly in M7's own section of
`docs/vision/roadmap.md`, and added a third real option to M7's own "package shape" decision item
(`presidium-contrib[civitas-gateway]`, alongside the previously-listed standalone-package and
`presidium-contrib[server]` options) — flagged as the option to evaluate first given how much
existing, tested infrastructure it reuses. Not committed to blindly: the same note calls out
re-verifying that `HTTPGateway`'s auth middleware composes cleanly with Presidium's own
grant/policy checks (not just transport-level authentication) before fully committing, rather than
assuming zero integration friction.

**Pages updated:**
- `docs/vision/roadmap.md` — M7 section, new finding + updated package-shape decision item
- `docs/log.md` — this entry

---

## [2026-08-22] fix | Real Ed25519 identity binding + civitas PyPI pin (P0 items 1 & 2)

**Trigger:** Executing the P0 sequence from "Implementation Priority" (added earlier this
session): fix the Ed25519 identity binding, then pin `civitas` to a real PyPI release. Both are
now done, tested, and committed — not just planned.

**Ed25519 identity binding**: `GovernedRuntime.start()` now generates/loads a real, persistent
`civitas.security.identity.AgentIdentity` per agent (`load_or_generate(name, key_dir)`, default
`key_dir=.presidium/keys`, overridable via `presidium.registry.key_dir` in topology YAML or the
constructor), and binds its real `public_key_b64()` into `AgentRecord.public_key` — no longer a
hardcoded `""`. `AgentRegistry` gained a real `verify_signature(name, data, signature) -> bool`,
backed by a new `presidium.identity.verify_agent_signature()` shared primitive (one crypto
implementation, not duplicated per backend), implemented in `InMemoryRegistry`, `SqliteRegistry`,
and `presidium-contrib`'s `PostgresAgentRegistry`. Fails closed as a plain boolean for every
failure mode (unknown agent, empty/malformed public key, missing `pynacl`, invalid signature) —
matches `has_grant()`'s own shape, never raises. 18 new tests using real Ed25519 keypairs, not
mocked crypto. `pynacl>=1.5` is now a direct, required `presidium` dependency.

**Real, concrete side effect caught during this work**: the first test run leaked real private
key files into the repo's own working directory (`.presidium/keys/`), because two existing
`GovernedRuntime.from_config()` integration tests didn't override `key_dir` and inherited the new
default. Fixed by pointing those tests at `tmp_path`, and added `.presidium/` to `.gitignore` as
defense in depth (real private key material must never be committable, even by accident from an
interactive run).

**`civitas` PyPI pin**: removed the workspace root's `[tool.uv.sources]` git override
(`branch = "main"`); bumped `presidium`'s own dependency `civitas>=0.3` → `civitas>=0.11.0` (real,
current, tested-against version, matching `civitas-io/fabrica`'s own precedent).

**A real, separate bug found and fixed as a direct consequence of the pin fix, not searched for
deliberately**: pinning to `civitas>=0.11.0` made `civitas`'s own real `py.typed` marker visible
for the first time in this workspace (it didn't exist when `presidium` was floating on an older
resolution). Three `# type: ignore[misc]  # civitas lacks py.typed` comments became genuinely
unused; removing them surfaced a real, previously-hidden bug the broad ignore had been masking:
`presidium_contrib.service.registry.RegistryServer` named its own governance registry
`self._registry`, **colliding with `civitas.process.AgentProcess`'s own reserved `_registry`
attribute** (used internally for `suspend()`/`resume()`, capability-based routing, and spawn-target
resolution). Confirmed exploitable, not theoretical: `civitas/supervisor.py` sets
`agent._registry = self._registry` when wiring any child into a real Supervisor tree — a
`RegistryServer` added to a live tree would have had its own governance registry silently
clobbered by Civitas's unrelated routing registry. Renamed to `self._agent_registry`. Also added
two real tests for this class's `verify_signature()` (previously untested — this file remains
part of the still-open, separate `service/*` 0%-coverage P0 item, not fully closed by this fix).

Also fixed adjacent to this: missing `mypy` override entries for `hvac`/`asyncpg` (no published
type stubs for either), found while re-running a clean `mypy` pass after the ignore-comment
removals.

**Verification**: all 462 tests (354 presidium core + 108 presidium-contrib) pass, 3x stable, zero
leaked files. `ruff check`/`ruff format --check`/`mypy --strict` all clean on both packages.
Coverage: presidium core 90.97% → 95.24%.

**Pages updated:**
- `docs/vision/roadmap.md` — both P0 items marked done with full detail, M7's own duplicate
  Ed25519 checklist item marked done and clarified (mTLS wiring itself still open)
- `CHANGELOG.md` — real entries under `[Unreleased]`
- `docs/log.md` — this entry

---

## [2026-08-22] fix | Service Mode 0%-coverage gap closed (P0 item 3) — a second real bug found

**Trigger:** Continuing the P0 execution sequence after items 1 (Ed25519 binding) and 2 (civitas
PyPI pin): close `presidium_contrib.service.policy`/`.registry`'s 0% test coverage before M7
builds a network layer on top of them.

**What was added**: `tests/unit/test_service_policy.py` and `tests/unit/test_service_registry.py`
(direct `handle_call()` invocation, fast and focused) plus
`tests/integration/test_service_mode_real_runtime.py` (a real end-to-end suite through an actual
`civitas.Runtime`/`Supervisor`, not a mock). The integration suite includes a dedicated regression
test for the `RegistryServer._registry` collision fixed earlier this session — it asserts
`civitas.process.AgentProcess`'s own real `_registry` (a `LocalRegistry` instance) survives real
Supervisor wiring untouched, and that `RegistryServer`'s own `_agent_registry` is a distinct, real
`InMemoryRegistry` — proving the fix holds structurally, not just that the attribute has a
different name now.

**A second real, previously-hidden bug found and fixed, not searched for deliberately**: the very
first test exercising a non-default-ALLOW policy decision through `PolicyEvaluatorServer` crashed
with `AttributeError: 'str' object has no attribute 'value'`. Root cause:
`PolicyEvaluatorServer._handle_load()` passed the raw JSON string (`"deny"`) straight into
`PolicyRule(decision=..., ...)` instead of converting it to the `PolicyDecision` enum first.
`CelPolicyEngine.evaluate()` doesn't type-check `rule.decision` at that layer, so it silently
returned the raw string on any DENY/REQUIRE_APPROVAL match; `PolicyEvaluatorServer`'s own
`_handle_evaluate()` then crashed trying to call `.value` on it. Fixed to match
`GovernedRuntime._parse_policy_rules()`'s own already-correct pattern
(`PolicyDecision(r.get("decision", "deny"))`). 0% test coverage on this file had let this ship
silently — this is exactly the class of bug closing a real coverage gap is meant to catch.

**Also fixed, found adjacent to this work**: four now-unused `# type: ignore[arg-type]` comments
in `test_postgres_registry.py` (a pre-existing file, not part of this session's earlier work) —
not part of the CI-gated `mypy` scope (`Makefile`/`ci.yml` only check `src/`, not `tests/`), fixed
anyway since it was found while re-running a clean `mypy` pass here. A separate, genuinely
pre-existing, out-of-scope set of dict-invariance mypy nits in `test_agentgateway_client.py` was
confirmed present in the baseline (before any of this session's changes) and left alone.

**Verification**: `presidium_contrib.service.policy`/`.registry` both now at **100% coverage**
(from 0%). `presidium-contrib` overall coverage: 71% → 82%. All 131 presidium-contrib tests pass,
3x stable. `ruff`/`mypy --strict` clean on `src/` (the real, CI-gated scope) for both packages.

**Pages updated:**
- `docs/vision/roadmap.md` — P0 item 3 marked done with full detail, M7's own duplicate
  checklist item updated to point at it
- `CHANGELOG.md` — real entries
- `docs/log.md` — this entry

---

## [2026-08-22] design | Default-deny for CelPolicyEngine's no-match case — direction decided, implementation deferred

**Trigger:** Mid-way through the M7 design walkthrough (specifically, deciding what `check_grant()`
should return when no policy matches a given resource), a direct, explicit preference was stated:
default DENY over default ALLOW, even at real UX cost, because it reduces blast radius.

**Real attempt made and reverted the same session, on purpose**: flipped `CelPolicyEngine.
evaluate()`'s no-rule-matched return from `ALLOW`/`"All policies passed"` to `DENY`/`HARD` and ran
the full test suite to find the real blast radius before committing to anything. **24 tests failed**
across `test_cel.py`, `test_governed_tool.py`, `test_governed_model.py`, and
`test_governed_runtime.py` — confirming this is not a small, local fix. Presidium's entire existing
test suite (and, by extension, its whole current policy-authoring model) assumes implicit
allow-by-default; almost none of the existing example/test policies declare an explicit terminal
ALLOW rule. Reverted cleanly (confirmed all 354 tests pass again) rather than force through a
change with this much real, uninvestigated ripple effect mid-design-session.

**Decision**: the *direction* (default-deny) is decided and recorded, not abandoned — but the
*implementation* is deliberately deferred as its own, dedicated piece of work, not bundled into M7.
Real, scoped follow-up items captured directly in `docs/vision/roadmap.md`'s P1 list: choose
hard-unconditional-deny vs. an opt-in `strict` parameter; update every existing example/test
policy set to add an explicit terminal ALLOW rule; update tutorial/quickstart content that would
otherwise silently start denying everything; reuse the already-drafted `DENY`/`HARD`/reason shape
when this is actually implemented.

**M7's own design proceeds using today's real, current behavior** (no-match → ALLOW) for now —
`check_grant()`'s documentation will note this default-deny direction as a known, real, pending
change to core policy semantics, not silently assume it's already in place.

**Pages updated:**
- `docs/vision/roadmap.md` — the P1 item rewritten with the real attempt, its findings, and the
  concrete follow-up work needed before implementing
- `docs/log.md` — this entry

---

## [2026-08-22] design | M7 design finalized — presidium-server-requirements.md + presidium-server.md

**Trigger:** A full, interactive design walkthrough for M7 (Presidium Server), per this project's
own "documentation-driven development" philosophy (design docs before implementation) and M7's
own roadmap checklist item calling for exactly these two docs.

**Real decisions made and recorded, each with its own rationale, not asserted flatly:**

1. **Architecture: wrap `GovernedRuntime` as one agent (Option A), not a distributed GenServer
   mesh (Option B).** `check_grant` needs registry lookup → policy evaluation → approval handling
   *composed together* — `GovernedRuntime`'s own object graph already does this correctly,
   in-process, tested. Recomposing it from the separately-deployed `PolicyEvaluatorServer`/
   `RegistryServer` GenServers would mean re-deriving working orchestration for no immediate
   benefit. Those GenServers remain valid for a genuinely distributed deployment later — not
   blocked by this choice.
2. **The `check_grant` action-mapping algorithm (Option 2, refined)**: `ActionRequest.resource =
   action` verbatim (the whole original string, colon included), `ActionRequest.action = "invoke"`
   fixed. Refined from an initial sketch that required a bespoke `"_run"`-suffix-stripping
   transform for one example (`"skill_run:skill_name"`) that wouldn't generalize.
3. **A real, new `GovernedToolProvider.check_grant()` method in `presidium` core** (not just
   server-side glue) — shares lookup/evaluate/audit logic with the existing `check()` via a new
   private helper, but returns immediately on `REQUIRE_APPROVAL` instead of blocking on
   `ApprovalService`, matching Fabrica's own suspend/resume expectations rather than Presidium's
   existing synchronous-approval assumption.
4. **mTLS clarification, correcting an earlier framing**: Civitas's real `require_client_cert` is
   X.509 subject-DN-allowlist based — a completely separate identity layer from `AgentRecord.
   public_key`'s raw Ed25519 keys. mTLS does not need to wait on `presidium-contrib[spiffe]`; it
   ships now with a simple, real private CA.
5. **`GET /health` is minimal and explicit**, not Civitas's auto-registered 11-route topology
   introspection surface — smallest attack surface consistent with the real job.
6. **Package shape**: `presidium_contrib.server`, a new module (extra: `presidium-contrib[server]`,
   needs `civitas[http]`).

**A real, separate decision surfaced and explicitly deferred mid-walkthrough**: default-deny for
`CelPolicyEngine`'s no-match case (see the immediately preceding log entry) — direction decided,
implementation reverted after a real attempt broke 24 tests, tracked as its own dedicated future
work. M7's design proceeds on today's real ALLOW-on-no-match behavior, documented as such (NFR-3),
not silently assumed already fixed.

**Real, pre-existing prior art found and reconciled, not duplicated**: `docs/design/http-gateway.md`
— an older, "TBD"/deferred draft that had already correctly identified "Civitas has an HTTP
Gateway, Presidium needs to extend it" but sat disconnected from any real milestone. Marked
superseded (kept for historical accuracy, not deleted), and its real, still-useful endpoint
sketches (approval queue, agent list/suspend, policy validate) folded into `presidium-server.md`'s
own "Deferred" section rather than re-derived from scratch. Also carries the same stale
`presidium-sdk` package-name issue already corrected elsewhere this session — left as written in
this specific file for historical accuracy, with a note explaining why.

**Pages added:**
- `docs/design/presidium-server-requirements.md` — FR-1 through FR-5, NFR-1 through NFR-3, Design
  Decisions table, Out of Scope
- `docs/design/presidium-server.md` — Architecture (with diagram), Data Model (real code sketches
  for `check_grant()`, `PresidiumGatewayAgent`, `GatewayConfig`), Deferred REST surface, Open
  Questions

**Pages updated:**
- `docs/vision/roadmap.md` — M7's design-docs checklist item and package-shape item marked done,
  the stale "reuse PolicyEvaluatorServer/RegistryServer's call protocol" bullet corrected to match
  the finalized Option A decision
- `docs/design/http-gateway.md` — marked superseded, historical status preserved
- `docs/index.md` — design docs table: two new rows, HTTP Gateway row updated
- `docs/log.md` — this entry (and the immediately preceding default-deny entry)

**Next real step**: implement `GovernedToolProvider.check_grant()` and `PresidiumGatewayAgent` per
these now-finalized docs.

---

## [2026-08-22] fix | Presidium Server implemented — check_grant() shipped, a real design gap found and fixed

**Trigger:** Continuing the P0 sequence past design: implement `GovernedToolProvider.check_grant()`
and `PresidiumGatewayAgent` per the just-finalized `presidium-server-requirements.md`/
`presidium-server.md`.

**`GovernedToolProvider.check_grant()`**: added as designed — shares lookup/evaluate/audit logic
with `check()` via a renamed, generalized private helper. **A real bug found immediately by the
first real test run, not by inspection**: the shared helper (then still named
`_evaluate_pre_tool`) always prefixed its resource argument with `"tool:"`, inherited from `check()`'s
own convention — silently breaking `check_grant()`'s own FR-1.3 "resource = action, verbatim"
requirement. Fixed by renaming the helper to `_evaluate`, having it take a pre-built `resource`
string directly, and having `check()` build `f"tool:{tool}"` itself before calling it —
`check_grant()`'s own second parameter renamed from `tool` to `resource` to match, resolving the
naming-mismatch open question from the design doc for real rather than leaving it as a comment.

**`presidium_contrib.server`**: implemented, then found a second, more structural real gap the
same session, this time via an actual running gateway, not a unit test. The design's original
`PresidiumGatewayAgent` dispatched on `message.payload["__op__"]`, injected via each route's
`payload_extra` — modeled directly on how Civitas's own auto-registered topology routes work.
A real `GET /health` against this design returned `400 {"error": "Unknown operation: None"}`.
Traced to the real, verified source: `civitas.gateway.router.RouteTable.from_config()` (the actual
parser for user-declared `routes:` config) never reads `payload_extra` at all — it is exclusively
populated by Civitas's own internal `_build_topology_routes()` construction, not a general-purpose
mechanism exposed through `GatewayConfig.routes`'s public, list-of-dicts shape. **Fixed with one
real agent per route** instead of one dispatching on a marker: `PresidiumGatewayAgent` now only
ever handles `check_grant`; a new, separate, minimal `HealthCheckAgent` handles `/health`.
Genuinely simpler than the original design, not just a workaround.

**Verification**: 39 new tests across `presidium`/`presidium-contrib` — real unit tests calling
`handle_call()` directly (fast, focused), plus a real end-to-end integration suite
(`tests/integration/test_presidium_server_real_gateway.py`) standing up an actual
`civitas.gateway.HTTPGateway` inside a real `civitas.Runtime`/`Supervisor` and hitting it with real
`httpx` requests over real HTTP — `GET /health`, `POST /v1/check_grant` (allow/deny/unresolvable
agent, all confirmed `200` never `5xx` per FR-1.2/NFR-1), and confirmed `/topology`/`/docs` return
`404` (proving FR-4.2's minimal-surface requirement holds for real, not just in the config). Both
new modules (`presidium.providers.tool` stays 100%; `presidium_contrib.server` reaches 100%) —
517 tests total across both packages, 3x stable. `ruff`/`mypy --strict` clean on both.

**Real, honest gaps not hidden**: `scope` (FR-1.4) is not yet threaded through to
`ActionRequest.parameters` — a small, real, scoped follow-up, not claimed done. A full mTLS
handshake integration test (real private CA + client cert) is not yet written — the current suite
exercises `require_mtls=False` end to end and `require_mtls=True`'s config assembly in isolation,
a real, separate, valuable addition tracked but not done here.

**Pages updated:**
- `docs/design/presidium-server.md` — the `PresidiumGatewayAgent`/`GatewayConfig` sketches
  replaced with the real, shipped code shape; a new "Implementation status" section; the resolved
  Open Questions updated
- `docs/vision/roadmap.md` — the implementation checklist item marked done with the full story,
  the `scope` gap tracked as its own item
- `CHANGELOG.md` — real entries
- `docs/log.md` — this entry

---

## [2026-08-22] fix | Drop-in Civitas ModelProvider/ToolProvider adapters shipped — P0 sequence complete

**Trigger:** The last item of the original five-item P0 sequence: make `GovernedModelProvider`/
`GovernedToolProvider` usable as drop-in Civitas `ModelProvider`/`ToolProvider`s, per RFC-001's
own stated purpose for them.

**Real design constraint found before writing code, not assumed**: neither
`civitas.plugins.model.ModelProvider.chat()` nor `civitas.plugins.tools.ToolProvider.execute()`
carries agent identity in its own call signature — `self.llm`/`self.tools` are typically shared
across a whole Supervisor tree (`agent.llm = self.llm` on spawn, per `civitas/supervisor.py`).
Confirmed a real, already-established precedent solves this exact problem elsewhere in the same
codebase: `civitas.process.AgentProcess.connect_mcp()` already constructs `MCPTool(client, schema,
..., agent_name=self.name)` — a per-agent-bound `ToolProvider` instance, built fresh for each
agent with its own identity closed over at construction time. Matched this pattern directly rather
than inventing a new one.

**Shipped**: `presidium.providers.civitas_adapters.GovernedModelProviderAdapter`/
`GovernedToolAdapter` — real structural `ModelProvider`/`ToolProvider` implementations (confirmed
via `mypy --strict`, neither Protocol is `@runtime_checkable` so structural typing is the only
real conformance check available). `GovernedRuntime.model_for(agent_name, backend)`/
`tool_for(agent_name, backend)` factory methods, mirroring Civitas's own `model_for()` naming.
DENY raises `PolicyDeniedError` — reusing `check()`'s existing, unmodified behavior exactly,
deliberately different from `check_grant()`'s non-raising design (an in-process exception through
the calling agent's own error boundary/supervision is the correct, idiomatic convention here;
there's no HTTP boundary to keep from raising across).

**A real architectural principle stated directly during the design conversation, worth recording
verbatim**: Civitas is generic and has no concept of governance; Presidium is the opinionated
layer that wraps a real backend with governance, on top of it, never replacing it. This is exactly
what these two adapters do — `backend: ModelProvider`/`backend: ToolProvider` is any real object
satisfying Civitas's own Protocols, and the adapter is *also* a real `ModelProvider`/`ToolProvider`
itself, so it can be dropped in anywhere the un-governed version could.

**Verification**: 13 new tests (`test_civitas_adapters.py` using real, minimal fake backends that
structurally satisfy Civitas's own Protocols — not mocks; plus `TestModelForToolFor` in
`test_governed_runtime.py`, confirming the factory methods wire the real, shared
`GovernedRuntime.model_provider`/`.tool_provider` state through correctly, not a fresh disconnected
instance). `civitas_adapters.py` at 100% coverage. All 377 presidium tests + 153 presidium-contrib
tests pass, 3x stable. `ruff`/`mypy --strict` clean.

**Scope note, precise, not overclaimed**: this solves "can these be a drop-in Civitas
`ModelProvider`/`ToolProvider`" — it does **not** build the separate, larger pluggable-vendor
`LLMGatewayBackend`/`ToolsGatewayBackend` abstraction from `docs/design/llm-gateway.md`/
`mcp-gateway.md` (AgentGateway/LiteLLM/etc. as swappable backends). That remains real, designed,
not built. `backend:` here can already be any object satisfying Civitas's real Protocols,
including a future pluggable-vendor adapter, without further changes to these two classes.

**All five items of the original P0 sequence (Ed25519 binding, civitas PyPI pin, `service/*`
coverage, M7/Presidium Server, this item) are now done.** A first real `presidium`/
`presidium-contrib` PyPI release can genuinely be considered — the fictional-cryptographic-
identity-claim blocker is resolved. M5 (CLI, docs site, examples) remains its own, separate,
real work, not automatically unblocked by this alone.

**Pages updated:**
- `docs/vision/roadmap.md` — the P0 item marked done with full detail; the "Recommended sequence"
  line updated to reflect all five items complete
- `CHANGELOG.md` — real entries
- `docs/log.md` — this entry

---

## [2026-08-22] release | v0.2.0 release prep — hardened CI, real README fixes, real bug found

**Trigger:** All five P0 items shipped; time to plan and prepare the first real, public PyPI
release for `presidium`/`presidium-contrib`.

**Real facts established first, not assumed:** confirmed via PyPI's own JSON API that neither
`presidium` nor `presidium-contrib` is taken (both 404). Checked Homebrew too (per direct request)
— both names also available there, but genuinely not relevant yet: Presidium is a `pip install`
library with no CLI/binary shipped (M5's CLI is designed, not built), and even `python-civitas`
itself (which has a real CLI) has no Homebrew presence — no org precedent for this pattern.
Decision: skip Homebrew now, revisit only if/when M5 ships and there's a real reason to want it.

**`ci.yml`/`publish.yml` already existed** (not built from scratch, unlike Fabrica's own CI this
session) — found real gaps versus the stricter convention already proven in `civitas-io/fabrica`'s
own live release: mutable action version tags instead of pinned commit SHAs; no CycloneDX SBOM
generation; `ci.yml`'s test matrix only covered Python 3.12/3.13 despite both packages' own
classifiers claiming 3.14 support too (fixed, all three now tested for real).

**A real, previously-untested bug found and fixed before trusting this workflow for a real
release, not assumed working**: `uv build` run with a bare `working-directory:
packages/presidium` (the pre-existing pattern) places its output in the *workspace root's*
`dist/`, not `packages/presidium/dist/` — confirmed with a real local build, not guessed. This
workflow had never actually run for a real tag push (no git tags existed before this session), so
the bug had never been caught. Fixed with `uv build --package <name> -o packages/<name>/dist`
from the workspace root.

**Version bump: `0.1.0` → `0.2.0`, not `0.1.0`.** `CHANGELOG.md` already had a real `[0.1.0] -
2026-06-14` entry documenting an earlier, never-published M2-completion snapshot — publishing the
real first release as `0.1.0` would have collided with it. `0.2.0` is the honest choice given the
real, substantial scope since that snapshot (M3 complete, M7 shipped end to end, drop-in adapters,
the Ed25519 fix) — a real minor version's worth of new features. `Development Status` classifier
bumped `2 - Pre-Alpha` → `3 - Alpha` to match, per `civitas-io/fabrica`'s own precedent.

**Real README inaccuracies found and fixed before going public**: a broken Civitas link pointing
at a personal GitHub account (`jerynmathew/python-civitas`) instead of the real org repo
(`civitas-io/python-civitas`), appearing twice; a `presidium-contrib[litellm]` extra listed as
installable in two places despite not existing in the real `pyproject.toml` — would have broken
for anyone who actually tried it; a stale status line (test counts, missing M7/adapter mentions).

**Real infrastructure created**: the `pypi` GitHub Environment on `civitas-io/presidium` (no
protection rules, matching `python-civitas`'s and `fabrica`'s own shape).

**Verification**: both packages build correctly with the corrected `uv build` invocation (real
local build, `dist/` lands in the right place); CycloneDX SBOM generation verified locally for
both; all 377 + 153 tests pass; `ruff`/`mypy --strict` clean; real GitHub Actions `CI` run
confirmed green on this exact commit, including the new Python 3.14 matrix entry.

**Still needed, tracked and not done here — requires a human with PyPI account access**: two real
PyPI "pending publisher" registrations (`presidium` and `presidium-contrib` are separate PyPI
projects) — owner `civitas-io`, repo `presidium`, workflow `publish.yml`, environment `pypi`.
Cannot be done via API.

**Pages updated:**
- `.github/workflows/publish.yml`/`ci.yml` — hardened
- `README.md`, `CHANGELOG.md` — real fixes and the new `[0.2.0]` entry
- `packages/presidium/pyproject.toml`/`packages/presidium-contrib/pyproject.toml` — version +
  classifier bumps
- `docs/log.md` — this entry

---

## [2026-08-22] fix | v0.2.1 — a real, live bug found only by actually verifying the published v0.2.0 wheel

**Trigger:** After `presidium` v0.2.0 published successfully to PyPI, the release process's own
final verification step (a fresh-venv `pip install` + real imports — the exact discipline this
project has followed for every real release, not a formality) caught a genuine, live bug: `import
presidium` failed entirely with `ModuleNotFoundError: No module named 'aiosqlite'`.

**Root cause**: `presidium/__init__.py` eagerly imports `SqliteRegistry` (for a nicer, top-level
public API), and `presidium/registry/sqlite.py` had an unconditional, module-level `import
aiosqlite` — but `aiosqlite` is declared only as the optional `[sqlite]` extra, never a core
dependency. A plain `pip install presidium` (the documented, base install — "`presidium` is the
only required dependency") therefore could not even be imported at all. This had never been
caught locally because every local dev/test environment already had `aiosqlite` installed via
`--all-extras`.

**Fixed** with the exact same lazy-import + helpful-error pattern `civitas.security.identity`
already uses for `pynacl` — moved the real `import aiosqlite` into a new `_require_aiosqlite()`
helper, called only inside `SqliteRegistry._conn()` (the one place it's genuinely needed, on first
real use), raising a real `PresidiumError` with an install hint if genuinely missing. The
type-only `aiosqlite.Row`/`aiosqlite.Connection` annotations moved into a `TYPE_CHECKING` guard —
safe because `from __future__ import annotations` already makes every annotation a lazily-
evaluated string at runtime, so mypy still sees the real types without requiring the import.

**Checked, not assumed: `presidium-contrib` does not have this bug.** Its own `__init__.py` is
empty and imports nothing eagerly — confirmed via the same real, fresh-venv verification. No fix
needed or shipped for `presidium-contrib`; it stays at v0.2.0.

**Verification, the real point of this whole entry**: a completely fresh venv, `pip install
packages/presidium` with `aiosqlite` genuinely absent (confirmed via a real, separate `import
aiosqlite` failing first) — `import presidium` and every real submodule import now succeed.
Re-installed `aiosqlite` and confirmed `SqliteRegistry` itself still works end to end (register +
lookup) once it's actually present. 3 new tests, including a cheap, precise, direct regression
guard (source-inspects the file for a reintroduced module-level `import aiosqlite`). All 380 tests
pass, 3x stable. `ruff`/`mypy --strict` clean.

**Versioned `0.2.1`, a real patch release** — a genuine bug fix, not a feature, released
immediately rather than left live and broken.

**Pages updated:**
- `packages/presidium/src/presidium/registry/sqlite.py` — the real fix
- `packages/presidium/tests/unit/registry/test_sqlite_lazy_import.py` — new tests
- `packages/presidium/pyproject.toml` — version bump
- `CHANGELOG.md` — real `[0.2.1]` entry
- `docs/log.md` — this entry

---

## [2026-08-22] feat | trust ceiling propagation + monotonic capability narrowing (AGT-comparison P1)

**Trigger:** Two real, concrete security gaps recorded as P1 items during an earlier session's
direct comparison against Microsoft's Agent Governance Toolkit (`microsoft/agent-governance-
toolkit`) — walked through in full with the user before implementing (design questions: where the
enforcement point lives, snapshot-vs-live-tracking, what "subset" means for a `Grant`, dangling-
parent handling, depth-limit default) before writing any code.

**Grounded in the real, current code first** — read all three `AgentRegistry` backends
(`InMemoryRegistry`, `SqliteRegistry`, `PostgresAgentRegistry`) and confirmed `AgentRecord.
parent_agent_id` was genuinely pure, unvalidated metadata; confirmed there is still no real
"spawn" composition anywhere in the system (Civitas's `Runtime.spawn()` has no Presidium
awareness; Fabrica's `CivitasBridge.request_supervision()` is a pass-through, not called by
Fabrica's own managers in v1) — so this closes a registry-API-level hole pre-emptively, not a live
exploit against a running feature.

**Shipped:**
- `AgentRecord.trust_ceiling: float | None` and `AgentRecord.depth: int` (new fields, additive).
- `LinearTrustScore(ceiling=...)` clamps `.value`'s getter. Deliberate decision, corrected once
  during implementation after a real test failure: `set_value()` (HUMAN_OVERRIDE) still respects
  the ceiling — a hard boundary, not a bypass. An admin who wants to grant more trust than a
  lineage permits must explicitly raise `AgentRecord.trust_ceiling` itself, a separate,
  deliberate administrative action.
- New `presidium.lineage` module: `compute_child_ceiling()`, `validate_grant_narrowing()`,
  `compute_child_depth()`, `DEFAULT_MAX_DELEGATION_DEPTH = 10` (AGT's own default, reused).
- New errors: `UnresolvableParentError`, `GrantEscalationError`, `DelegationDepthExceededError`.
- Enforced inside `register()` **and** `add_grant()` on all three registry backends — defense in
  depth at the registry API itself, not an opt-in helper a caller could skip. A dangling
  `parent_agent_id` fails closed.
- `max_delegation_depth` is a configurable, keyword-only constructor param on all three
  registries, backward compatible (existing positional call sites unaffected).

**Real bugs found and fixed during implementation, before landing:**
- A TOCTOU race in the first draft of `SqliteRegistry.add_grant()`/`PostgresAgentRegistry.
  add_grant()`: resolving the parent outside the write lock, then re-acquiring it to append the
  grant, left a window for the record to change in between. Fixed by resolving the parent inside
  the single lock scope for the whole operation (safe: `lookup_by_id()` never tries to reacquire
  the same lock).
- Duplicated tier-threshold logic inline in `SqliteRegistry.register()`/`PostgresAgentRegistry.
  register()` instead of reusing the existing `presidium.trust.tier_for_value()` — caught before
  committing, not after.
- The `set_value()`/ceiling interaction above — my first design comment claimed HUMAN_OVERRIDE
  bypasses the ceiling, but the actual `value` getter clamps unconditionally regardless of write
  path. Caught by a real, failing test, not by re-reading my own docstring. Resolved by changing
  the *design*, not silently patching the test to match unintended behavior: ceiling now
  correctly, deliberately applies even to overrides.
- An off-by-one in the delegation-depth-limit test itself (asserted rejection at exactly the
  default limit, which correctly is *not* rejected — only *exceeding* it is).

**Verification**: 60+ new tests — pure-function unit tests (`test_lineage.py`), registry-level
integration tests parametrized over `InMemoryRegistry`/`SqliteRegistry` via the shared `registry`
fixture, and mock-based `PostgresAgentRegistry` tests proving the exact same shared
`presidium.lineage` functions are used (not a divergent reimplementation for that backend). All
439 `presidium` + 158 `presidium-contrib` tests pass, 3x stable. `ruff`/`mypy --strict` clean on
both packages' `src/`. Coverage: `presidium.lineage` 100%; new code paths in all three registries
fully exercised — remaining coverage gaps in `postgres.py` are pre-existing (`connect()`,
`deregister()`, etc.), confirmed via direct diff, not introduced by this change.

**Pages updated:**
- `packages/presidium/src/presidium/lineage.py` (new)
- `packages/presidium/src/presidium/model.py`, `errors.py`, `trust/core.py`
- `packages/presidium/src/presidium/registry/{memory,sqlite}.py`
- `packages/presidium-contrib/src/presidium_contrib/registry/postgres.py`
- New/updated tests across both packages
- `docs/vision/roadmap.md` — both P1 items marked done with full detail
- `CHANGELOG.md` — new `[Unreleased]` entry
- `docs/log.md` — this entry
