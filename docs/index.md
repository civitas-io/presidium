# Presidium Wiki Index

> Content catalog for the Presidium knowledge base.
> AI assistants: read this file first to find relevant pages before drilling in.
> Last updated: 2026-04-30

**The governed agent platform built on [Civitas](https://github.com/jerynmathew/python-civitas).**

Runtime + governance as one architecture — not bolted on, not a sidecar, native.

**Status:** Pre-alpha. Documentation-first phase.

---

## Vision

*Why Presidium exists, where it sits in the market, and where it's going.*

| Page | Summary |
|---|---|
| [Manifesto](vision/manifesto.md) | Core thesis: governance should be architectural, not bolted on. 88% of agents fail in production due to infrastructure, not models. Principles: OSS-first, Python-native, developer-centric, vendor-neutral. |
| [Market Positioning](vision/positioning.md) | Competitive 2x2 (governance depth × runtime depth). Presidium occupies the only empty quadrant. Detailed comparisons vs. AGT, Fiddler, Temporal. Target users: platform engineers, agent developers, enterprise compliance. |
| [Roadmap](vision/roadmap.md) | Six milestones: M1 (docs, current) → M2 (registry + policy) → M3 (gateways) → M4 (eval) → M5 (SDK) → M6 (cloud). |

## Architecture

*How the system fits together — components, boundaries, integration points.*

| Page | Summary |
|---|---|
| [System Overview](architecture/overview.md) | Full system architecture diagram (Mermaid). Four key design decisions: governance as supervisor constraints, registry as source of truth, gateways as Civitas plugins, eval as feedback loop. Data flow and startup sequence. |
| [Package Map](architecture/packages.md) | Six planned packages with responsibilities, Civitas integration points, key types (Protocol sketches), and dependency rules. Packages: registry, policy, llm-gateway, mcp-gateway, eval, sdk. |
| [Full Stack](architecture/stack.md) | Three-layer model: Run (Civitas) → Govern (Presidium) → Observe (Fiddler/Arize). Integration points between layers. Three deployment scenarios (laptop → staging → production). |

## Design

*Per-component design docs — problem, goals, API sketches, alternatives.*

| Page | Package | Milestone | Status |
|---|---|---|---|
| [Agent Registry](design/agent-registry.md) | `presidium-registry` | M2 | Draft |
| [Policy Engine](design/policy-engine.md) | `presidium-policy` | M2 | Draft |
| [LLM Gateway](design/llm-gateway.md) | `presidium-llm-gateway` | M3 | Draft |
| [MCP Gateway](design/mcp-gateway.md) | `presidium-mcp-gateway` | M3 | Draft |
| [Eval Framework](design/eval-framework.md) | `presidium-eval` | M4 | Draft |
| [HTTP Gateway](design/http-gateway.md) | TBD | M4+ | Draft (deferred) |

## Research

*Competitive analysis, market data, and strategic context. Living documents — updated as new information arrives.*

| Page | Summary | Key Data Points |
|---|---|---|
| [Competitive Landscape](research/competitive-landscape.md) | Detailed analysis of Temporal ($5B), Microsoft AGT (1,289 stars, 540K LOC), Fiddler ($100M), LangChain ($1.25B), CrewAI ($18M), Inngest, Restate. Nobody occupies the runtime + governance quadrant. | 7 competitors analyzed |
| [Market Analysis](research/market-analysis.md) | Agent infrastructure market $7-11B in 2026, 27-47% CAGR. 88% of agents fail to reach production. 67% cite auditability as top adoption barrier. Tool call failure rates 3-15%. | 12 data sources cited |
| [Monetization Strategy](research/monetization.md) | Open core + managed cloud playbook. Temporal/LangChain/CrewAI revenue comparisons. Four-tier pricing model. Revenue projections Y1-Y4. Defensible moats analysis. | 5 comparable companies |
| [Fiddler Relationship](research/fiddler-relationship.md) | Complementary, not competitive. Fiddler observes agents (layer above), Presidium runs them (layer below). Natural pipeline: Presidium generates telemetry → Fiddler analyzes. Watch areas: "control plane" branding, policy enforcement direction. | Stack position analysis |

## RFCs

*Significant decisions requiring explicit scope definition.*

| RFC | Title | Status |
|---|---|---|
| [RFC-001](rfcs/001-presidium-scope.md) | Presidium Scope and Boundaries | Draft |

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
