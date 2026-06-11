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
