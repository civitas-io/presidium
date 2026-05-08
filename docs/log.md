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
