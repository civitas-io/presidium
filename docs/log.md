# Wiki Log

> Append-only chronological record of wiki operations.
> Each entry uses the format: `## [YYYY-MM-DD] operation | description`
> Parseable with: `grep "^## \[" docs/log.md | tail -10`

---

## [2026-04-30] init | Repository created with documentation-first approach

**Sources ingested:**
- python-civitas repository (GitHub: jerynmathew/python-civitas) — evaluated architecture, code quality, documentation, testing, security
- Microsoft Agent Governance Toolkit (GitHub: microsoft/agent-governance-toolkit) — evaluated as competitor, 540K LOC, 9 packages, 10/10 OWASP
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
