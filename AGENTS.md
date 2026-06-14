# AGENTS.md — Presidium

> Machine-readable project reference for AI coding assistants.
> Last updated: 2026-06-11

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
- CNCF-aligned where applicable (SPIFFE for identity, OTEL for telemetry, CEL for policy)

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
├── packages/                        # Code packages (uv workspace members)
│   ├── presidium/                   # Interface library (protocols, dataclasses, CEL engine)
│   │   └── src/presidium/
│   │       ├── protocols/           # Python Protocols for every component
│   │       ├── models/              # Shared dataclasses (AgentRecord, Policy, etc.)
│   │       └── policy/             # CEL policy engine (default implementation)
│   └── presidium-contrib/           # Adapters + reference implementations
│       └── src/presidium_contrib/
│           ├── opa/                 # OPA adapter (presidium-contrib[opa])
│           ├── openbao/             # OpenBao/Vault credential backend (presidium-contrib[openbao])
│           ├── agentgateway/         # AgentGateway adapter (presidium-contrib[agentgateway])
│           ├── slack/               # Slack HITL adapter (presidium-contrib[slack])
│           ├── registry/            # Reference impl: Agent Registry with grants + trust
│           ├── mcp_gateway/         # Reference impl: MCP governance gateway
│           └── trust/               # Reference impl: Trust scoring engine
├── docs/                            # All documentation
│   ├── vision/                      # Why — manifesto, positioning, roadmap
│   ├── architecture/                # How — system design, package map
│   ├── design/                      # What — per-component design docs
│   ├── research/                    # Context — competitive analysis, market
│   ├── rfcs/                        # RFCs for significant decisions
│   └── guides/                      # Getting started, contributing
├── AGENTS.md                        # This file
├── pyproject.toml                   # Root workspace config
└── mkdocs.yml                       # Documentation site
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

- **Package names:** `presidium` and `presidium-contrib` (hyphenated in pyproject, underscore in Python imports: `presidium_contrib`)
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

# Core interfaces and models
from presidium.protocols import RegistryProtocol
from presidium.models import AgentRecord

# Contrib adapter (optional extra)
from presidium_contrib.registry import InMemoryRegistry
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

### `presidium` — Interface Library

The core package. Contains only protocols, dataclasses, and the CEL policy engine (the one default implementation). Nothing else.

| Module | Owns |
|---|---|
| `presidium.protocols` | Python `Protocol` classes for every component (Registry, PolicyEngine, LLMGateway, MCPGateway, Evaluator, CredentialStore) |
| `presidium.models` | Shared dataclasses: `AgentRecord`, `Policy`, `Grant`, `TrustScore`, `LLMRequest`, `ToolCall`, etc. |
| `presidium.policy` | CEL policy engine — the default `PolicyEngine` implementation. No other implementations live here. |

Install: `pip install presidium`

### `presidium-contrib` — Adapters and Reference Implementations

All concrete implementations. Organized into two categories:

**Adapters** (wrapping existing products):

| Extra | Module | Wraps |
|---|---|---|
| `[opa]` | `presidium_contrib.opa` | Open Policy Agent — for teams already running OPA |
| `[openbao]` | `presidium_contrib.openbao` | OpenBao (Vault-compatible, MPL 2.0, OpenSSF) — credential management |
| `[agentgateway]` | `presidium_contrib.agentgateway` | AgentGateway (Linux Foundation) — LLM + MCP + A2A routing with CEL policies |
| `[slack]` | `presidium_contrib.slack` | Slack — human-in-the-loop approvals |

**Reference Implementations** (novel components, no prior art to wrap):

| Module | Implements | Why here |
|---|---|---|
| `presidium_contrib.registry` | `RegistryProtocol` | Agent Registry with grants + trust scores — no existing product models this |
| `presidium_contrib.mcp_gateway` | `MCPGatewayProtocol` | MCP governance — MCP is new, no tooling exists |
| `presidium_contrib.trust` | `TrustScoringProtocol` | Trust scoring engine — novel concept |

Install: `pip install presidium-contrib[opa,openbao]` (mix and match extras)

### Dependency Rules

1. `presidium` may depend on `civitas` and `cel-python` only
2. `presidium` must not depend on `presidium-contrib` or any adapter library
3. `presidium-contrib` depends on `presidium` (for protocols and models)
4. `presidium-contrib` adapter extras depend on their respective backends (opa, hvac/openbao, agentgateway, slack-sdk) as optional dependencies
5. No circular dependencies
6. No package should import from another package's `_internal` modules

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
5. **Vendor lock-in** — No hard dependency on any cloud provider or observability vendor
6. **Break package boundaries** — Don't import from `_internal` modules across packages
7. **Skip design docs** — No package implementation without an approved design doc in `docs/design/`
8. **Monolith creep** — Each package should be independently installable
9. **Implement governance logic in `presidium` core** — The core package is interface-only. Protocols and dataclasses only. The CEL engine is the single permitted exception (it's the default implementation). Everything else goes in `presidium-contrib`.

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
| **CEL** | Common Expression Language. Embeddable policy language used by Kubernetes and Google Cloud IAM. Evaluates in microseconds in-process. The default policy engine in `presidium`. |
| **Interface Library** | A package whose primary value is the contracts it defines (Python `Protocol` classes, dataclasses), not the implementations. `presidium` is an interface library. |
| **Adapter** | A concrete implementation of a `presidium` protocol that wraps an existing product (OPA, OpenBao, AgentGateway). Lives in `presidium-contrib`. |
| **Reference Implementation** | A concrete implementation of a `presidium` protocol for a component where no mature product exists to wrap. Lives in `presidium-contrib`. |
| **Library Mode** | Running a component in-process as a Python import. No network calls, no sidecar, microsecond latency. The default for all Presidium components. |
| **Service Mode** | Running a component as a standalone HTTP service or GenServer for distributed deployments. Optional. The interface is identical to library mode. |
