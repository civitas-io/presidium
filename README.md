# Presidium

**The governed agent platform built on [Civitas](https://github.com/civitas-io/python-civitas).**

Runtime + governance as one architecture. Not bolted on, not a sidecar, native.

---

[![PyPI - presidium](https://img.shields.io/pypi/v/presidium?label=presidium)](https://pypi.org/project/presidium/)
[![PyPI - presidium-contrib](https://img.shields.io/pypi/v/presidium-contrib?label=presidium-contrib)](https://pypi.org/project/presidium-contrib/)
[![GitHub release](https://img.shields.io/github/v/release/civitas-io/presidium)](https://github.com/civitas-io/presidium/releases)

```bash
pip install presidium              # core: policy, registry, trust, credentials
pip install presidium-contrib      # adapters: OPA, OpenBao, Slack, Postgres, the M7 server, ...
```

> **Status:** Alpha, real and tested, not just designed. M1–M3 complete. **M7 (Presidium
> Server) shipped in full for its P0 scope plus three of its four originally-deferred REST
> extensions** (2026-08-22 through 2026-08-24): `GovernedRuntime`'s governance is reachable over
> real REST+mTLS (`presidium-contrib[server]`) -- `check_grant()`, registry CRUD
> (register/list/get/deregister agents), approval list/decide, and rate limiting (reusing
> Civitas's own first-party G4 limiter) are all real and released. Satisfies
> [`civitas-io/fabrica`](https://github.com/civitas-io/fabrica)'s `PresidiumClient.check_grant()`
> contract exactly -- verified against Fabrica's own real `RestPresidiumClient`. `AgentGatewayClient`
> (`presidium-contrib[agentgateway]`) speaks real MCP tool calls AND real A2A agent delegation
> over Streamable HTTP, not LLM routing alone. `presidium-contrib[spiffe]` adds real SPIRE-issued
> X.509-SVID identity alongside the default Ed25519 binding. `GovernedModelProvider`/
> `GovernedToolProvider` are real, pure-authorization wrappers (`check()`/`check_grant()`, not
> `chat()`/`execute()` themselves) — `presidium.providers.civitas_adapters`'s
> `GovernedModelProviderAdapter`/`GovernedToolAdapter` are the real, drop-in Civitas
> `ModelProvider`/`ToolProvider` implementations that compose them with a real backend.
> `CelPolicyEngine` fails closed on no policy match by default (a real, documented breaking
> change from earlier releases). Trust ceiling propagation and monotonic capability narrowing on
> delegation/spawn are shipped. **M5 (SDK + CLI) started the same day**: a real `presidium`
> command (`pip install presidium-contrib[sqlite]`) -- `presidium version`, `registry list`,
> `policy validate`, `trust replay` -- mirroring `civitas`'s own CLI shape exactly. `Grant.
> condition` is now really evaluated (was a documented dead field) and
> `presidium.providers.civitas_adapters` gained `governed_spawn_check()`/
> `GovernedDynamicSupervisor`, gating `DynamicSupervisor.on_spawn_requested` -- both real,
> external findings, verified and fixed the same day they were reported. 743 tests
> (487 `presidium` + 256 `presidium-contrib`), mypy strict, ruff clean. Only credential
> resolution remains undone from M7's original scope.

## What Is Presidium?

Presidium is a governance layer for AI agent systems, built natively on top of the [Civitas](https://github.com/civitas-io/python-civitas) agent runtime. Where Civitas provides Erlang/OTP-style supervision trees, message passing, and transport abstraction, Presidium adds:

- **Agent Registry** — identity, capabilities, trust tracking with grants
- **Policy Engine** — CEL-based declarative policies enforced as supervisor constraints
- **LLM Gateway** — rate limiting, cost tracking, model routing
- **MCP Gateway** — tool access governance, poisoning detection
- **Eval Framework** — governance-aware evaluation with external exporter support

Presidium is an **interface library first**. The core package (`presidium`) defines protocols and dataclasses. Implementations ship as adapters in `presidium-contrib`. You can swap backends without touching your governance logic.

## Why?

88% of AI agents fail to reach production ([TURION.AI, 2026](https://turion.ai/blog/state-of-ai-agents-enterprise-adoption-2026/)). The failures aren't model quality. They're infrastructure: no fault tolerance, no policy enforcement, no observability, no governance.

Existing solutions address halves of the problem:
- **Runtimes** (Temporal, Civitas) run agents reliably but don't govern them
- **Governance tools** (Microsoft AGT, Fiddler) govern agents but don't run them

Presidium is the first platform where **governance and runtime are the same thing**.

## Project Structure

```
presidium/
├── docs/
│   ├── vision/          # Why Presidium exists
│   ├── architecture/    # How it all fits together
│   ├── design/          # Per-component design docs
│   ├── research/        # Competitive analysis, market research
│   ├── rfcs/            # Request for Comments
│   └── guides/          # Getting started, contributing
├── packages/            # Code packages
│   ├── presidium/       # Interface library (protocols, CEL engine, scoring library)
│   └── presidium-contrib/  # Adapters + reference implementations
├── AGENTS.md            # AI assistant instructions
└── pyproject.toml       # Workspace config
```

## Command-Line Interface

```bash
pip install presidium-contrib[sqlite]  # CLI + local SqliteRegistry support
```

```bash
presidium version                                   # show presidium + presidium-contrib versions
presidium registry list --db registry.db            # list agents in a local SqliteRegistry file
presidium policy validate topology.yaml              # validate a CEL policy YAML file
presidium trust replay --events e.json --spec s.json # deterministic trust-score replay (FR-5.3)
```

Mirrors `civitas`'s own CLI shape exactly (Typer + Rich). **Real, honest scope**: `registry
list`/`policy validate` operate on local files, not a live `presidium-server` yet (a real,
named follow-up); `trust show`/`trust events` (querying a *live* agent's history) aren't built
-- no registry backend today persists a durable, queryable trust-event history to query in the
first place.

## Packages

| Package | Purpose | Install | Status |
|---|---|---|---|
| `presidium` | Protocols, dataclasses, CEL policy engine, scoring library, trust scoring, `GovernedRuntime`, drop-in `ModelProvider`/`ToolProvider` adapters | `pip install presidium` | M1–M3 complete |
| `presidium-contrib` | Real network server (`presidium-contrib[server]`, M7: check_grant, registry CRUD, approval list/decide, rate limiting), adapters for OPA/OpenBao/AgentGateway/SPIFFE/Slack/Webhook/Postgres; reference impls for Agent Registry, MCP governance, trust scoring, service mode | `pip install presidium-contrib[opa]` | M1–M3 complete; M7 (Presidium Server) shipped, minus credential resolution |

`presidium` is the only required dependency. `presidium-contrib` extras are opt-in:

```
presidium-contrib[server]        # Presidium Server (M7) — check_grant, registry CRUD, approval list/decide, rate limiting, over real REST+mTLS
presidium-contrib[opa]           # OPA adapter (for teams already running OPA)
presidium-contrib[openbao]       # OpenBao credential backend (Vault-compatible, MPL 2.0)
presidium-contrib[agentgateway]  # AgentGateway (Linux Foundation) — real LLM + real MCP tools + real A2A delegation
presidium-contrib[spiffe]        # Real SPIRE-issued X.509-SVID identity (opt-in alongside the Ed25519 default)
presidium-contrib[slack]         # Slack-based human-in-the-loop
presidium-contrib[webhook]       # Webhook-based approval provider
presidium-contrib[postgres]      # PostgreSQL agent registry backend
presidium-contrib[sqlite]        # presidium CLI's `registry list` command (forwards to presidium[sqlite])
```

**Real, current gap, not hidden**: a `LLMGatewayBackend`/`ToolsGatewayBackend` *pluggable-vendor*
abstraction (letting AgentGateway/LiteLLM/etc. be swapped as interchangeable backends) is designed
(see [`docs/design/llm-gateway.md`](docs/design/llm-gateway.md) and
[`docs/design/mcp-gateway.md`](docs/design/mcp-gateway.md)) but not built — there is no
`presidium-contrib[litellm]` extra yet, despite earlier drafts of this README describing one.
Kong, Portkey, Cloudflare AI Gateway, Helicone, TrueFoundry are stubbed in the design docs only,
not built either. `AgentGatewayClient` (`presidium-contrib[agentgateway]`) is real today for
all three surfaces: LLM chat/list_models, real MCP `list_tools`/`call_tool` over Streamable
HTTP, and real A2A agent delegation.

### Library Mode vs. Service Mode

Every component starts as a library. You import it, it runs in-process, evaluation takes microseconds. When you outgrow in-process (distributed deployments, multi-tenant isolation), some components can optionally deploy as a service. The interface stays the same either way.

### CNCF-Aligned Standards

Presidium prefers CNCF standards where applicable to enable enterprise adoption and interoperability:
- **Identity**: [SPIFFE](https://spiffe.io/)-compatible agent identity URIs with Ed25519 cryptographic binding
- **Observability**: [OpenTelemetry](https://opentelemetry.io/) for all telemetry (via Civitas)
- **Policy**: [CEL](https://cel.dev) (Common Expression Language) — the Kubernetes admission policy language

### Policy Engine: CEL by Default

The default policy engine is CEL. CEL is embeddable as a library, evaluates in microseconds with no sidecar, and is already the policy language for Kubernetes admission webhooks and Google Cloud IAM. If you already run OPA infrastructure, `presidium-contrib[opa]` wraps it as an adapter.

### Where Presidium Builds vs. Wraps

Mature products exist for some components. Presidium wraps them:

| Component | Backend | How |
|---|---|---|
| Policy engine | CEL (default), OPA (adapter) | `presidium-contrib[opa]` |
| Credential management | OpenBao (Vault-compatible, MPL 2.0, OpenSSF) | `presidium-contrib[openbao]` |
| LLM routing | AgentGateway (reference, real, LLM-side only) | `presidium-contrib[agentgateway]` (LiteLLM is a designed, not-yet-built, leading 2nd-pick candidate — no extra exists yet) |
| MCP + A2A routing | AgentGateway (sole backend today) | `presidium-contrib[agentgateway]` |
| Human-in-the-loop | Slack, Webhook | `presidium-contrib[slack]` |

For components where prior art exists but isn't packaged as a standalone, swappable library to wrap, Presidium ships reference implementations in `presidium-contrib`:

| Component | Why a reference impl |
|---|---|
| Agent Registry with grants + trust scores | Prior art exists (Google Gemini registry, Microsoft AGT) but not as a swappable Python library |
| MCP governance gateway | Existing MCP gateways (incl. Microsoft AGT's MCP Security Gateway) aren't standalone libraries to wrap |
| Trust scoring | Mature models exist (e.g. Microsoft AGT, 0–1000 scale) but none ship as a reusable library |

## Relationship to Civitas

Civitas is the **runtime**. Presidium is the **governance layer**. They share the same org and philosophy but are separate projects. The package structure mirrors Civitas directly: `civitas` (protocols + defaults) and `civitas-contrib` (provider implementations) map to `presidium` and `presidium-contrib`.

- Civitas handles: supervision trees, message passing, transport, crash recovery, OTEL tracing
- Presidium handles: policy enforcement, agent identity, gateways, eval, compliance
- Together: the only platform where governance is architectural, not an afterthought

## License

[Apache License 2.0](LICENSE)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [getting started guide](docs/guides/getting-started.md).
