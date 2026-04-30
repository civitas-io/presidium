# AGENTS.md — Presidium

> Machine-readable project reference for AI coding assistants.
> Last updated: 2026-04-30

## Project Identity

**Presidium** is a governed agent platform built on [Civitas](https://github.com/jerynmathew/python-civitas).
It provides governance infrastructure — policy enforcement, agent identity, gateways, and eval —
natively integrated into the Civitas agent runtime.

- **Repository:** `github.com/civitas-io/presidium`
- **Organization:** `civitas-io`
- **License:** Apache 2.0
- **Python:** ≥3.12
- **Status:** Pre-alpha (documentation-first phase)

### What Presidium Is

- A governance layer for AI agent systems
- Built natively on Civitas (supervision trees, message passing, transports)
- Policies as supervisor constraints, not external interceptors
- Python-first, developer-centric, vendor-neutral

### What Presidium Is NOT

- NOT a replacement for Civitas — it depends on Civitas
- NOT an observability platform — that's Fiddler, Arize, Langfuse (Presidium generates telemetry they consume)
- NOT a framework for building agents — that's LangGraph, CrewAI, OpenAI Agents SDK
- NOT a Microsoft AGT competitor — different layer (runtime-native vs. sidecar)

---

## Monorepo Structure

```
presidium/
├── packages/                   # Code packages (uv workspace members)
│   ├── presidium-registry/     # Agent identity, capabilities, trust
│   ├── presidium-policy/       # Policy engine (YAML, OPA, Cedar)
│   ├── presidium-llm-gateway/  # LLM routing, rate limiting, cost
│   ├── presidium-mcp-gateway/  # Tool access governance
│   ├── presidium-eval/         # Governance-aware evaluation
│   └── presidium-sdk/          # Unified API (pip install presidium)
├── docs/                       # All documentation
│   ├── vision/                 # Why — manifesto, positioning, roadmap
│   ├── architecture/           # How — system design, package map
│   ├── design/                 # What — per-component design docs
│   ├── research/               # Context — competitive analysis, market
│   ├── rfcs/                   # RFCs for significant decisions
│   └── guides/                 # Getting started, contributing
├── AGENTS.md                   # This file
├── pyproject.toml              # Root workspace config
└── mkdocs.yml                  # Documentation site
```

---

## Conventions

### Matching civitas-forge Patterns

This repo follows the conventions established in `civitas-io/civitas-forge`:

| Convention | Standard |
|---|---|
| Package manager | uv (Astral) |
| Build backend | hatchling |
| Python version | ≥3.12, tested on 3.12, 3.13, 3.14 |
| Linting | Ruff, 100 char line length |
| Rule sets | E, F, I, UP, B, ASYNC |
| Type checking | mypy strict, `disallow_untyped_defs = true` |
| Testing | pytest + pytest-asyncio |
| Async mode | `asyncio_mode = "auto"` |
| License | Apache 2.0 |
| Package layout | `packages/<name>/src/<name>/` |
| RFCs | `docs/rfcs/<number>-<title>.md` |
| Design docs | `docs/design/<feature>.md` |

### Naming

- **Package names:** `presidium-<component>` (hyphenated in pyproject, underscore in Python imports)
- **Module names:** lowercase, single word where possible
- **Classes:** PascalCase
- **Functions/methods:** snake_case
- **Constants:** UPPER_SNAKE_CASE
- **Type aliases:** PascalCase

### Imports

```python
# Standard library
from __future__ import annotations
import asyncio
from typing import Protocol

# Third-party
from civitas import AgentProcess, Runtime

# Local package
from presidium_registry import AgentRecord
```

Order: stdlib → third-party → local. Enforced by Ruff `I` rules.

### Type Safety

- All code must pass `mypy --strict`
- No `# type: ignore` without explanatory comment
- No `Any` without justification
- Use `Protocol` for plugin interfaces (structural typing, not inheritance)
- Use `@dataclass` for data containers

### Error Handling

- Define custom exception hierarchies per package
- Never use bare `except:` or `except Exception:`
- Errors at package boundaries should be wrapped in package-specific exceptions
- Follow Civitas's `ErrorAction` pattern (RESTART, STOP, ESCALATE) where applicable

### Testing

- Unit tests: `packages/<name>/tests/unit/`
- Integration tests: `packages/<name>/tests/integration/`
- Fixtures: reusable test helpers in `conftest.py`
- Coverage target: 85% minimum per package
- Async tests use `pytest-asyncio` with auto mode

---

## Package Boundaries

| Package | Owns | Depends On |
|---|---|---|
| `presidium-registry` | Agent identity, capability registration, trust scores, lifecycle tracking | civitas (registry, process) |
| `presidium-policy` | Policy definitions, evaluation engine, enforcement hooks | civitas (supervisor, bus) |
| `presidium-llm-gateway` | LLM provider routing, rate limiting, cost tracking, content filtering | civitas (plugins) |
| `presidium-mcp-gateway` | Tool access control, tool poisoning detection, credential redaction | civitas (mcp) |
| `presidium-eval` | Governance-aware evaluation, scoring, external exporter integration | civitas (eval_loop, plugins) |
| `presidium-sdk` | Unified public API, convenience imports, CLI | All packages above |

### Dependency Rules

1. Packages may depend on `civitas` (external)
2. Packages may depend on `presidium-registry` (shared identity)
3. `presidium-sdk` depends on all packages
4. No circular dependencies between packages
5. No package should import from another package's internal modules

---

## Anti-Patterns

### DO NOT:

1. **Suppress types** — No `as Any`, `@ts-ignore`, `# type: ignore` without comment
2. **Empty catch blocks** — Never `except: pass` or `except Exception: pass`
3. **Over-abstract** — No helpers/utilities for one-time operations
4. **Duplicate Civitas** — Don't reimplement supervision, messaging, or transport
5. **Vendor lock-in** — No hard dependency on any cloud provider or observability vendor
6. **Break package boundaries** — Don't import from `_internal` modules across packages
7. **Skip design docs** — No package implementation without an approved design doc in `docs/design/`
8. **Monolith creep** — Each package should be independently installable

---

## Wiki Maintenance

This project uses the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — `docs/` is a persistent, compounding knowledge base maintained by AI assistants. The wiki gets richer with every source ingested and every question asked. **You (the AI) own the wiki's maintenance. The human curates sources and asks questions.**

### Key Files

- **`docs/index.md`** — Content catalog. Read this FIRST on any query to find relevant pages. Updated on every ingest.
- **`docs/log.md`** — Append-only chronological log. Every ingest, query-filing, and lint pass gets an entry.

### Ingest Workflow

When the human provides new information (article, competitor update, market data, design decision, Civitas API change):

1. **Read the source** and discuss key takeaways with the human
2. **Update existing wiki pages** that the new information affects — don't just create new pages, revise what's already there:
   - Competitive data → update `docs/research/competitive-landscape.md`
   - Market numbers → update `docs/research/market-analysis.md`
   - Fiddler news → update `docs/research/fiddler-relationship.md`
   - Architecture insight → update relevant `docs/architecture/` and `docs/design/` pages
   - Scope change → update `docs/rfcs/001-presidium-scope.md`
3. **Create new pages** only if the topic genuinely doesn't fit in existing pages
4. **Update `docs/index.md`** — add/revise the entry for every page touched
5. **Append to `docs/log.md`** — record what was ingested, what pages were updated, key decisions made
6. **Update AGENTS.md** if conventions, structure, or glossary changed

A single source may touch 5-15 wiki pages. That's expected.

### Query Workflow

When the human asks a question against the wiki:

1. **Read `docs/index.md`** to find relevant pages
2. **Read those pages** and synthesize an answer with citations
3. **If the answer is valuable and reusable** (comparison, analysis, synthesis), offer to file it as a new wiki page
4. Filed answers go in the appropriate `docs/` subdirectory
5. Update `docs/index.md` and append to `docs/log.md`

### Lint Workflow

Periodically (or when the human asks), health-check the wiki:

- **Stale data** — market numbers with dates that have passed, competitor stats that may have changed (star counts, funding, versions)
- **Contradictions** — pages that disagree with each other due to sequential updates
- **Orphan pages** — pages not linked from `docs/index.md` or from other pages
- **Missing pages** — concepts mentioned frequently but lacking their own page
- **Missing cross-references** — pages that should link to each other but don't
- **Data gaps** — areas where a web search could fill in missing information

Report findings to the human. Fix mechanical issues (broken links, index updates) directly. Flag substantive issues (contradictions, stale claims) for discussion.

---

## PR Checklist

Before merging:

- [ ] Design doc exists in `docs/design/` for new packages
- [ ] All code passes `ruff check` and `ruff format --check`
- [ ] All code passes `mypy --strict`
- [ ] Tests pass with ≥85% coverage
- [ ] No new dependencies without justification
- [ ] AGENTS.md updated if conventions or structure changed
- [ ] CHANGELOG.md updated

---

## Glossary

| Term | Definition |
|---|---|
| **Agent** | An autonomous AI process managed by Civitas (AgentProcess) |
| **Registry** | The system tracking agent identities, capabilities, and trust |
| **Policy** | A declarative rule governing what an agent can/cannot do |
| **Trust Score** | A numeric measure of an agent's reliability/compliance history |
| **Gateway** | A routing layer that mediates access to LLMs or tools |
| **Eval** | Governance-aware evaluation of agent behavior and outputs |
| **Supervisor** | Civitas component managing agent lifecycle and fault tolerance |
| **Transport** | Civitas abstraction for message delivery (InProcess, ZMQ, NATS) |
| **Control Plane** | Industry term for governance infrastructure (Fiddler's positioning) |
| **Presidium** | Latin: "garrison, guard, protection" — governance for agent systems |
