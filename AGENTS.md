# AGENTS.md — Presidium

> Machine-readable project reference for AI coding assistants.
> Last updated: 2026-05-05

## Project Identity

**Presidium** is a governance layer for AI agent systems, built on [Civitas](https://github.com/civitas-io/civitas-forge).
It provides policy enforcement, agent identity, authorization, gateways, and compliance audit —
natively integrated into the Civitas agent runtime.

- **Repository:** `github.com/civitas-io/presidium`
- **Organization:** `civitas-io`
- **License:** Apache 2.0
- **Python:** ≥3.12
- **Status:** Pre-alpha (documentation-first phase)

### The One-Line Separation

> **Civitas:** Run agents reliably.
> **Presidium:** Run agents accountably.

These are additive. A customer never chooses between a Civitas feature and a Presidium feature for the same job. Civitas is complete and useful without Presidium. Presidium is meaningless without Civitas.

### What Presidium IS

- A governance layer for AI agent systems — policy, identity, credentials, gateways, audit
- Built natively on Civitas (supervision trees, message passing, transports)
- Governance as supervisor constraints, not external interceptors
- Python-first, developer-centric, vendor-neutral

### What Presidium Is NOT

- NOT a replacement for Civitas — it depends on Civitas
- NOT an Identity Provider — it integrates with Entra, Okta, Google IAM, AWS IAM; it does not issue identity tokens
- NOT an observability platform — that's Fiddler, Arize, Langfuse (Presidium generates governance telemetry they consume)
- NOT a framework for building agents — that's LangGraph, CrewAI, OpenAI Agents SDK
- NOT a content safety / guardrails tool — that's Fiddler Guardrails, NeMo Guardrails

---

## Monorepo Structure

```
presidium/
├── packages/                   # Code packages (uv workspace members)
│   ├── presidium-registry/     # Agent identity, grants, credential vault, trust
│   ├── presidium-policy/       # Policy engine (YAML, Cedar, OPA)
│   ├── presidium-llm-gateway/  # Rate limits, cost tracking, grant-based routing
│   ├── presidium-mcp-gateway/  # Tool ACLs, OAuth 2.1, poisoning detection
│   ├── presidium-audit/        # Governance metrics, compliance, export
│   └── presidium-sdk/          # Unified API (pip install presidium)
├── docs/                       # All documentation
│   ├── vision/                 # Why — manifesto, positioning, roadmap
│   ├── architecture/           # How — system design, package map
│   ├── design/                 # What — per-component design docs
│   ├── research/               # Context — competitive analysis, AAA patterns, market
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
| `presidium-registry` | Agent identity, grants (authorization entitlements), credential vault, trust scores, IdP integration, token exchange | civitas (RegistryListener, AgentProcess lifecycle) |
| `presidium-policy` | Policy definitions, Cedar/OPA evaluation engine, enforcement hooks | civitas (Supervisor, MessageBus), presidium-registry |
| `presidium-llm-gateway` | Governed LLM access: per-agent rate limits, cost tracking, budget enforcement, grant-based provider routing | civitas (ModelProvider protocol), presidium-registry, presidium-policy |
| `presidium-mcp-gateway` | Governed tool access: tool ACLs, MCP OAuth 2.1, poisoning detection, credential redaction, HITL integration | civitas (MCPClient, ToolProvider protocol), presidium-registry, presidium-policy |
| `presidium-audit` | Governance metrics, compliance reporting, trust score feedback, external exporter integration | civitas (AuditSink, EvalLoop, ExportBackend), presidium-registry, presidium-policy |
| `presidium-sdk` | Unified public API (`GovernedRuntime`), CLI, YAML topology extension | All packages above, civitas |

### Dependency Rules

1. Packages may depend on `civitas` (external runtime)
2. Most packages depend on `presidium-registry` (shared identity + grants)
3. `presidium-sdk` depends on all packages
4. No circular dependencies between packages
5. No package should import from another package's internal modules

### The Eight Civitas Integration Points

Presidium extends Civitas at exactly these surfaces. Outside them, the layers are independent:

| # | Hook | What Presidium does |
|---|------|-------------------|
| 1 | `RegistryListener` | Populates `AgentRecord` on agent register/deregister |
| 2 | `ModelProvider` protocol | `GovernedModelProvider` wraps any provider with governance |
| 3 | `ToolProvider` protocol | `GovernedToolProvider` wraps MCP client with ACLs + OAuth |
| 4 | `AuditSink` | Enriches events with governance context; routes to exporters |
| 5 | `ExportBackend` | Implements Fiddler, Arize, Langfuse exporters |
| 6 | `EvalLoop` hooks | Attaches governance metrics alongside self-correction signals |
| 7 | Credential context injection | Populates agent startup context with credentials + grants |
| 8 | Durable suspension | Sends resume signal after HITL approval decision |

---

## Anti-Patterns

### DO NOT:

1. **Suppress types** — No `as Any`, `# type: ignore` without explanatory comment
2. **Empty catch blocks** — Never `except: pass` or `except Exception: pass`
3. **Over-abstract** — No helpers/utilities for one-time operations
4. **Duplicate Civitas** — Don't reimplement supervision, messaging, or transport
5. **Implement an IdP** — Integrate with Entra, Okta, Google IAM, AWS IAM; don't build one
6. **Vendor lock-in** — No hard dependency on any cloud provider or observability vendor
7. **Break package boundaries** — Don't import from `_internal` modules across packages
8. **Skip design docs** — No package implementation without an approved design doc in `docs/design/`
9. **Monolith creep** — Each package should be independently installable
10. **Conflate grants with capability tags** — Civitas `AgentProcess.capabilities` = routing tags; Presidium `AgentRecord.grants` = authorization entitlements. Do not mix these up.

---

## Wiki Maintenance

This project uses the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) — `docs/` is a persistent, compounding knowledge base maintained by AI assistants.

### Key Files

- **`docs/index.md`** — Content catalog. Read this FIRST on any query to find relevant pages. Updated on every ingest.
- **`docs/log.md`** — Append-only chronological log. Every ingest, query-filing, and lint pass gets an entry.

### Ingest Workflow

When the human provides new information (article, competitor update, market data, design decision, Civitas API change):

1. **Read the source** and discuss key takeaways with the human
2. **Update existing wiki pages** that the new information affects:
   - Competitive data → `docs/research/competitive-landscape.md`
   - Market numbers → `docs/research/market-analysis.md`
   - AAA / auth patterns → `docs/research/aaa-patterns.md`
   - Architecture insight → relevant `docs/architecture/` and `docs/design/` pages
   - Scope change → `docs/rfcs/001-presidium-scope.md`
3. **Create new pages** only if the topic genuinely doesn't fit existing pages
4. **Update `docs/index.md`** — add/revise entry for every page touched
5. **Append to `docs/log.md`** — record what was ingested, pages updated, decisions made
6. **Update AGENTS.md** if conventions, structure, or glossary changed

### Query Workflow

1. **Read `docs/index.md`** to find relevant pages
2. **Read those pages** and synthesize an answer with citations
3. If the answer is valuable and reusable, offer to file it as a new wiki page

### Lint Workflow

Periodically health-check the wiki:
- Stale data, contradictions, orphan pages, missing cross-references, data gaps

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
| **Agent** | An autonomous AI process managed by Civitas (`AgentProcess`) |
| **Grant** | A Presidium authorization entitlement — what an agent is *permitted to access* (e.g. `tool:database:read`, `llm:claude-sonnet`). Distinct from Civitas capability routing tags. |
| **Capability tag** | A Civitas routing tag on `AgentProcess` — what an agent *can handle technically* for message routing. NOT an authorization concept. |
| **Registry** | The Presidium system tracking persistent agent identity, grants, and trust |
| **Policy** | A declarative rule governing what an agent can/cannot do (ALLOW / DENY / REQUIRE_APPROVAL) |
| **Trust Score** | A numeric measure (0.0–1.0) of an agent's reliability/compliance history |
| **Credential Vault** | Presidium store of OAuth tokens and API keys scoped per `(agent_id, user_id)` tuple |
| **Gateway** | A governed wrapper over a Civitas plugin — `GovernedModelProvider` or `GovernedToolProvider` |
| **Audit** | Governance metrics and compliance reporting (`presidium-audit`) — external accountability, not internal quality |
| **Supervisor** | Civitas component managing agent lifecycle and fault tolerance |
| **Transport** | Civitas abstraction for message delivery (InProcess, ZMQ, NATS) |
| **OBO** | On-Behalf-Of (RFC 8693) — token exchange pattern where agent acts on behalf of a specific user |
| **HITL** | Human-in-the-Loop — approval workflow where a policy decision is `REQUIRE_APPROVAL` |
| **LITL** | Lies-in-the-Loop — attack where malicious content manipulates an approval dialog |
| **Presidium** | Latin: "garrison, guard, protection" — governance for agent systems |
