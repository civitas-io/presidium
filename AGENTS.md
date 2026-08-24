# AGENTS.md — Presidium

> Machine-readable project reference for AI coding assistants.
> Last updated: 2026-08-24 — corrected to match the real, current code (see "Real vs. previously
> documented" note below the monorepo tree; this file had drifted significantly since 2026-06-16).

## Project Identity

**Presidium** is a governance layer for AI agent systems, built on [Civitas](https://github.com/civitas-io/civitas-forge).
It provides policy enforcement, agent identity, authorization, gateways, and compliance audit —
natively integrated into the Civitas agent runtime.

- **Repository:** `github.com/civitas-io/presidium`
- **Organization:** `civitas-io`
- **License:** Apache 2.0
- **Python:** ≥3.12
- **Status:** Real, live, public PyPI packages —
  [`presidium`](https://pypi.org/project/presidium/) (v0.4.0) and
  [`presidium-contrib`](https://pypi.org/project/presidium-contrib/) (v0.7.0), 469 and 256 real
  tests respectively, including a real CLI (`presidium version`/`registry list`/`policy
  validate`/`trust replay`). See [`HANDOFF.md`](HANDOFF.md) for the current, dated status; this
  file describes structure and conventions, not point-in-time progress -- exact test counts and
  versions will drift again as work continues; treat these as "as of 2026-08-24," not a promise
  to keep updating on every single commit.

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

**Real, verified directly against the current source tree (2026-08-24) -- do not trust an older
copy of this section over `find packages/*/src -maxdepth 2`.**

```
presidium/
├── packages/                        # Code packages (uv workspace members)
│   ├── presidium/                   # Interface library (protocols, dataclasses, CEL engine)
│   │   └── src/presidium/
│   │       ├── policy/              # CEL policy engine (default implementation), default-deny
│   │       ├── providers/           # GovernedModelProvider/GovernedToolProvider (pure
│   │       │                        #   authorization), GatewayModelProvider/GatewayToolProvider
│   │       │                        #   (wraps a real gateway process), civitas_adapters.py
│   │       │                        #   (direct in-process Civitas ModelProvider/ToolProvider)
│   │       ├── registry/            # AgentRegistry Protocol + InMemory/Sqlite implementations
│   │       ├── scoring/             # Domain-agnostic scoring library (events, functions, config, spec)
│   │       ├── trust/               # Trust scoring (core, protocols, windowed, cold_start, telemetry)
│   │       ├── bus.py               # GovernedMessageBus (PRE_MESSAGE enforcement)
│   │       ├── model.py             # Shared dataclasses (AgentRecord, Policy, etc.) -- note:
│   │       │                        #   singular `model.py`, not a `models/` package
│   │       ├── errors.py            # PresidiumError hierarchy
│   │       ├── approval.py          # ApprovalService Protocol + CallbackApprovalProvider
│   │       ├── audit.py             # AuditSink/AuditEnricher Protocols + InProcessAuditEnricher
│   │       ├── credentials.py       # CredentialProvider Protocol + Env/File defaults
│   │       ├── identity.py          # verify_agent_signature() -- Ed25519 (default) + EC P-256
│   │       │                        #   (SPIFFE SVID) dispatch on AgentRecord.public_key_algorithm
│   │       ├── lineage.py           # Trust ceiling propagation + monotonic capability narrowing
│   │       └── runtime.py           # GovernedRuntime (from_config, reload_policies)
│   └── presidium-contrib/           # Adapters + reference implementations
│       └── src/presidium_contrib/
│           ├── cli/                 # presidium CLI (Typer + Rich) -- version, registry list,
│           │                        #   policy validate, trust replay ([project.scripts])
│           ├── opa/                 # OPA adapter (presidium-contrib[opa])
│           ├── openbao/             # OpenBao credential backend (presidium-contrib[openbao])
│           ├── agentgateway/        # AgentGateway adapter (presidium-contrib[agentgateway]) --
│           │                        #   real MCP tool-side (list_tools/call_tool) AND real A2A
│           │                        #   delegation (delegate_to_agent()), both over Streamable
│           │                        #   HTTP / a2a-sdk
│           ├── spiffe/              # SPIRE Workload API bridge (presidium-contrib[spiffe]) --
│           │                        #   real X.509-SVID identity, sync + rotation
│           ├── slack/               # Slack HITL adapter (presidium-contrib[slack])
│           ├── webhook/             # Webhook approval adapter (presidium-contrib[webhook])
│           ├── registry/            # Reference impl: PostgresAgentRegistry (presidium-contrib[postgres])
│           ├── mcp_gateway/         # Reference impl: tool poisoning, credential redaction, PII
│           │                        #   masking, plus GovernedMcpToolPipeline composing all three
│           │                        #   into one real, invokable pipeline
│           ├── trust/               # Reference impl: LearningTrustScorer
│           ├── server/              # M7 Presidium Server (presidium-contrib[server]) -- real
│           │                        #   REST+mTLS governance gateway: check_grant, registry CRUD
│           │                        #   (register/list/get/deregister), approval list/decide,
│           │                        #   rate limiting, over an actual civitas.gateway.HTTPGateway
│           └── service/             # Service mode: PolicyEvaluatorServer, RegistryServer (GenServer)
├── docs/                            # All documentation
│   ├── vision/                      # Why — manifesto, positioning, roadmap
│   ├── architecture/                # How — system design, package map
│   ├── design/                      # What — per-component design docs (+ vendor research docs)
│   ├── research/                    # Context — competitive analysis, market
│   ├── rfcs/                        # RFCs for significant decisions
│   └── guides/                      # Getting started, contributing
├── AGENTS.md                        # This file
├── pyproject.toml                   # Root workspace config
└── mkdocs.yml                       # Documentation site
```

**Real vs. previously documented -- corrected 2026-08-24:** the `litellm`/`kong`/`portkey`/
`cloudflare_ai_gateway`/`helicone`/`truefoundry` adapter modules and their matching
`presidium-contrib` extras described in earlier revisions of this file **do not exist in code**.
They were designed and evidence-compared (`docs/design/llm-gateway.md`), never built -- a real
P1 backlog item, not a stub shipped under those names. `AgentGateway` is the one real, shipped
`LLMGatewayBackend`/`ToolsGatewayBackend` reference adapter. Don't `pip install
presidium-contrib[litellm]` expecting it to work -- it will fail; that extra was never declared.


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

# Core interfaces and models -- real, verified module names (not presidium.protocols/.models,
# which don't exist)
from presidium.registry import AgentRegistry
from presidium.model import AgentRecord

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

The core package. Contains protocols, dataclasses, the CEL policy engine (the one default
implementation), and identity/lineage logic that every deployment needs regardless of which
contrib adapters it uses. Protocols are NOT centralized in a `presidium.protocols` module — that
module doesn't exist. Each Protocol lives next to the component it describes (e.g. `AgentRegistry`
in `registry/_base.py`, `PolicyEngine` in `policy/_base.py`, `LLMGatewayBackend`/
`ToolsGatewayBackend` in `providers/gateway.py`). Dataclasses live in the singular `model.py`, not
a `models/` package.

| Module | Owns |
|---|---|
| `presidium.model` | Shared dataclasses: `AgentRecord`, `Policy`, `Grant`, `TrustScore`, etc. |
| `presidium.policy` | CEL policy engine — the default `PolicyEngine` implementation, default-deny on no match. No other implementations live here. |
| `presidium.providers` | `GovernedModelProvider`/`GovernedToolProvider` (pure authorization), `GatewayModelProvider`/`GatewayToolProvider` (wraps a real, separate gateway process), `civitas_adapters` (direct in-process Civitas `ModelProvider`/`ToolProvider` wrapping) — three distinct composition patterns, not one |
| `presidium.registry` | `AgentRegistry` Protocol + `InMemoryRegistry`/`SqliteRegistry` |
| `presidium.identity` | `verify_agent_signature()` — dispatches on `AgentRecord.public_key_algorithm` (`"ed25519"` default, `"ec_p256"` for SPIFFE SVIDs) |
| `presidium.lineage` | Trust ceiling propagation + monotonic capability narrowing across agent delegation |

Install: `pip install presidium`

### `presidium-contrib` — Adapters and Reference Implementations

All concrete implementations. Organized into three categories: adapters, reference
implementations, and `presidium_contrib.cli` (the `presidium` command-line tool -- `[project.
scripts] presidium = "presidium_contrib.cli:main"`, Typer + Rich, mirroring `civitas.cli`'s own
package structure exactly). Not a wrapped product or a reference implementation of a protocol --
a real, separate, operational surface. See its own module docstring for the current, honest
command list and scope boundaries (`trust show`/`trust events` are deliberately not built yet).

**Adapters** (wrapping existing products):

| Extra | Module | Wraps |
|---|---|---|
| `[opa]` | `presidium_contrib.opa` | Open Policy Agent — for teams already running OPA |
| `[openbao]` | `presidium_contrib.openbao` | OpenBao (Vault-compatible, MPL 2.0, OpenSSF) — credential management |
| `[agentgateway]` | `presidium_contrib.agentgateway` | AgentGateway (Linux Foundation) — reference `LLMGatewayBackend` + `ToolsGatewayBackend`. **Real, shipped: LLM chat/list_models, MCP tool-side** (`list_tools()`/`call_tool()` over Streamable HTTP), **and A2A delegation** (`delegate_to_agent()`, real `a2a-sdk` client) |
| `[spiffe]` | `presidium_contrib.spiffe` | SPIRE Workload API (`spiffe` SDK) — real X.509-SVID identity sync + rotation into an `AgentRegistry`, opt-in alongside the Ed25519 default |
| `[slack]` | `presidium_contrib.slack` | Slack — human-in-the-loop approvals |
| `[webhook]` | `presidium_contrib.webhook` | Generic webhook — human-in-the-loop approvals |
| `[postgres]` | `presidium_contrib.registry` | `PostgresAgentRegistry` — a durable `AgentRegistry` backend |
| `[server]` | `presidium_contrib.server` | M7 Presidium Server — real REST+mTLS governance gateway (check_grant, registry CRUD, approval list/decide, rate limiting) over an actual `civitas.gateway.HTTPGateway` (wraps `civitas[http]`, not a third-party product, but genuinely optional) |
| `[sqlite]` | -- | Forwards to `presidium[sqlite]` (`aiosqlite`) -- needed by the `presidium` CLI's `registry list` command, not a `presidium-contrib`-owned module of its own |

**Not yet built, despite earlier documentation implying otherwise — corrected 2026-08-24**: no
`litellm`/`kong`/`portkey`/`cloudflare_ai_gateway`/`helicone`/`truefoundry` modules or extras
exist. They were designed and evidence-compared in `docs/design/llm-gateway.md`; AgentGateway is
the one real, shipped `LLMGatewayBackend`, and covers the reference path for now (not urgent per
`docs/vision/roadmap.md`'s own P1 list).

**Reference Implementations** (components with no standalone library to wrap):

| Module | Implements | Why here |
|---|---|---|
| `presidium_contrib.registry` | `AgentRegistry` | Agent Registry with grants + trust scores — prior art exists (Google Gemini, AGT) but not as a swappable library |
| `presidium_contrib.mcp_gateway` | MCP governance | Tool poisoning detection, credential redaction, PII masking, plus `GovernedMcpToolPipeline` composing all three into one real, invokable pipeline — existing gateways (incl. AGT) aren't standalone libraries to wrap |
| `presidium_contrib.trust` | `TrustScorer` | Trust scoring engine (`LearningTrustScorer`) — mature models exist (e.g. AGT) but none ship as a reusable library |

Install: `pip install presidium-contrib[opa,openbao]` (mix and match extras)

### Dependency Rules

1. `presidium` core dependencies are `civitas`, `cel-python`, `pynacl`, and `cryptography` —
   the last two back Ed25519 (default) and EC P-256 (SPIFFE) identity verification respectively.
   Both are real, hard, always-installed dependencies, lazily imported at the call site for
   graceful degradation, never a separate optional extra — same precedent for both.
2. `presidium` must not depend on `presidium-contrib` or any adapter library
3. `presidium-contrib` depends on `presidium` (for protocols and models)
4. `presidium-contrib` adapter extras depend on their respective backends (opa, hvac/openbao,
   mcp/agentgateway, spiffe, slack-sdk, asyncpg/postgres, civitas[http]/server) as optional
   dependencies
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
| **Audit** | Governance metrics and compliance reporting (`AuditSink`/`AuditEnricher` in `presidium`, not a separate `presidium-audit` package) — external accountability, not internal quality |
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
