# Presidium Wiki Index

> Content catalog for the Presidium knowledge base.
> AI assistants: read this file first to find relevant pages before drilling in.
> Last updated: 2026-06-12

**The governed agent platform built on [Civitas](https://github.com/jerynmathew/python-civitas).**

Runtime + governance as one architecture — not bolted on, not a sidecar, native.

**Status:** Pre-alpha. M2 implementation complete (Phases 1-6). Civitas integration remaining.

---

## Vision

*Why Presidium exists, where it sits in the market, and where it's going.*

| Page | Summary |
|---|---|
| [Manifesto](vision/manifesto.md) | Core thesis: governance should be architectural, not bolted on. 88% of agents fail in production due to infrastructure, not models. Principles: OSS-first, Python-native, developer-centric, vendor-neutral. |
| [Market Positioning](vision/positioning.md) | Competitive 2x2 (governance depth × runtime depth). Presidium occupies the only empty quadrant. Detailed comparisons vs. AGT, Fiddler, Temporal. Target users: platform engineers, agent developers, enterprise compliance. |
| [Roadmap](vision/roadmap.md) | Six milestones: M1 (docs, complete) → M2 (core interfaces + CEL policy) → M3 (contrib adapters + reference impls) → M4 (autonomy progression) → M5 (SDK) → M6 (cloud). |

## Architecture

*How the system fits together — components, boundaries, integration points.*

| Page | Summary |
|---|---|
| [System Overview](architecture/overview.md) | Full system architecture diagram (Mermaid). Seven key design decisions: governance as supervisor constraints, registry as source of truth, gateways as Civitas plugins, eval as feedback loop, interface-first architecture, CEL as default policy language, library-first service-optional. Data flow and startup sequence. |
| [Package Map](architecture/packages.md) | Two-package structure: `presidium` (protocols + CEL defaults) and `presidium-contrib` (adapters for OPA/Vault/LiteLLM/Slack + reference impls for novel components). Component map, Protocol definitions, dependency graph. |
| [Full Stack](architecture/stack.md) | Three-layer model: Run (Civitas) → Govern (Presidium) → Observe (Fiddler/Arize). Library mode vs service mode deployment. Three deployment scenarios with YAML topology examples (laptop → staging → production). |
| [Architecture Diagrams](assets/) | SVG assets: interface-first-architecture, deployment-modes, autonomy-progression, product-mapping, policy-evaluation-flow, full-stack-layers, eval-architecture, deepeval-integration, test-harness-architecture |

## Design

*Per-component design docs — problem, goals, API sketches, alternatives.*

| Page | Package | Milestone | Status |
|---|---|---|---|
| [Agent Registry](design/agent-registry.md) | `presidium` (protocol) + `presidium-contrib` (Postgres ref impl) | M2 | Draft |
| [Agent Registry Requirements](design/agent-registry-requirements.md) | `presidium` (protocol) | M2 | Draft |
| [Policy Engine](design/policy-engine.md) | `presidium` (protocol + CEL default) + `presidium-contrib[opa]` | M2 | Draft |
| [Policy Engine Requirements](design/policy-engine-requirements.md) | `presidium` (protocol + CEL default) | M2 | Draft |
| [Credential Provider Requirements](design/credential-provider-requirements.md) | `presidium` (protocol) | M2 | Draft |
| [Credential Provider](design/credential-provider.md) | `presidium` (protocol + env/file) / `presidium-contrib` (Vault, AWS) | M2 | Draft |
| [Approval Service Requirements](design/approval-service-requirements.md) | `presidium` (protocol) | M2 | Draft |
| [Approval Service](design/approval-service.md) | `presidium` (protocol + callback) / `presidium-contrib` (Slack, Temporal, webhook) | M2 | Draft |
| [Audit Enricher Requirements](design/audit-enricher-requirements.md) | `presidium` (protocol) | M2 | Draft |
| [Audit Enricher](design/audit-enricher.md) | `presidium` (protocol + InProcessAuditEnricher) | M2 | Draft |
| [Topology Integration Requirements](design/topology-integration-requirements.md) | `presidium` + `civitas` (2 minimal changes) | M2 | Draft |
| [Topology Integration](design/topology-integration.md) | `presidium` (GovernedRuntime) | M2 | Draft |
| [Implementation Plan](design/implementation-plan.md) | All M2 components | M2 | Phases 1-6 complete |
| [LLM Gateway](design/llm-gateway.md) | `presidium` (protocol) + `presidium-contrib[litellm]` | M3 | Draft |
| [MCP Gateway](design/mcp-gateway.md) | `presidium` (protocol) + `presidium-contrib` (ref impl) | M3 | Draft |
| [Eval Framework](design/eval-framework.md) | `presidium` + `civitas[test]` | M4 | Draft (revised) |
| [DeepEval Integration](design/deepeval-integration.md) | `civitas-contrib[deepeval]` | M4 | Draft |
| [HTTP Gateway](design/http-gateway.md) | TBD | M4+ | Draft (deferred) |

## Research

*Competitive analysis, market data, and strategic context. Living documents — updated as new information arrives.*

| Page | Summary | Key Data Points |
|---|---|---|
| [Competitive Landscape](research/competitive-landscape.md) | Detailed analysis of Temporal ($5B), Microsoft AGT (1,289 stars, 540K LOC), Fiddler ($100M), LangChain ($1.25B), CrewAI ($18M), Inngest, Restate. Nobody occupies the runtime + governance quadrant. | 7 competitors analyzed |
| [Market Analysis](research/market-analysis.md) | Agent infrastructure market $7-11B in 2026, 27-47% CAGR. 88% of agents fail to reach production. 67% cite auditability as top adoption barrier. Tool call failure rates 3-15%. | 12 data sources cited |
| [Monetization Strategy](research/monetization.md) | Open core + managed cloud playbook. Temporal/LangChain/CrewAI revenue comparisons. Four-tier pricing model. Revenue projections Y1-Y4. Defensible moats analysis. | 5 comparable companies |
| [Fiddler Relationship](research/fiddler-relationship.md) | Complementary, not competitive. Fiddler observes agents (layer above), Presidium runs them (layer below). Natural pipeline: Presidium generates telemetry → Fiddler analyzes. Watch areas: "control plane" branding, policy enforcement direction. | Stack position analysis |
| [Agent Registry Research](research/agent-registry-research.md) | Industry research on agent identity, registration, authorization, and trust across AWS Bedrock, Google Gemini, Microsoft AGT, IBM watsonx, SPIFFE/SPIRE, K8s RBAC, OAuth 2.0, and 4 academic papers. Comparative analysis and 8 key patterns. | 4 providers + 3 infra systems + 4 papers |

## RFCs

*Significant decisions requiring explicit scope definition.*

| RFC | Title | Status |
|---|---|---|
| [RFC-001](rfcs/001-presidium-scope.md) | Presidium Scope and Boundaries | Draft |
| [RFC-002](rfcs/002-multi-dimensional-evaluation.md) | Multi-Dimensional Evaluation for Non-Deterministic Systems | Seed |

## Guides

| Page | Summary |
|---|---|
| [Getting Started](guides/getting-started.md) | Add governance to a Civitas agent system in under 5 minutes. Programmatic and YAML examples. |

## Project Files

*Root-level documents outside docs/.*

| File | Purpose |
|---|---|
| [AGENTS.md](../AGENTS.md) | Machine-readable project reference for AI assistants. Conventions, anti-patterns, PR checklist. |
| [README.md](../README.md) | Public-facing project overview. |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | How to contribute (currently: feedback on design docs). |
| [SECURITY.md](../SECURITY.md) | Vulnerability reporting policy. |
| [CHANGELOG.md](../CHANGELOG.md) | Release history. |
| [pyproject.toml](../pyproject.toml) | Workspace configuration (uv, Ruff, mypy, pytest). |

## Maintenance

This wiki follows the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — a persistent, compounding knowledge base maintained by AI assistants.

- **Ingest workflow:** When new sources arrive, update relevant pages across the wiki (see AGENTS.md § Wiki Maintenance)
- **Query workflow:** Synthesize answers from wiki pages; file valuable answers as new pages
- **Lint workflow:** Periodically check for stale data, contradictions, orphan pages, missing cross-references
- **Log:** All wiki operations are recorded in [log.md](log.md)
