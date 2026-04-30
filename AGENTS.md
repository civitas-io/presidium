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
