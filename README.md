# Presidium

**The governed agent platform built on [Civitas](https://github.com/civitas-io/python-civitas).**

Runtime + governance as one architecture. Not bolted on, not a sidecar, native.

---

> **Status:** Alpha, real and tested, not just designed. M1–M3 complete. **M7 (Presidium Server)
> shipped**: `GovernedRuntime`'s governance is now reachable over real REST+mTLS
> (`presidium-contrib[server]`), satisfying [`civitas-io/fabrica`](https://github.com/civitas-io/fabrica)'s
> `PresidiumClient.check_grant()` contract exactly — verified end to end through an actual
> `civitas.gateway.HTTPGateway`. `GovernedModelProvider`/`GovernedToolProvider` are also real,
> drop-in Civitas `ModelProvider`/`ToolProvider` implementations now
> (`presidium.providers.civitas_adapters`). 530 tests (377 `presidium` + 153
> `presidium-contrib`), 95.69%/83% coverage, mypy strict, ruff clean.

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

## Packages

| Package | Purpose | Install | Status |
|---|---|---|---|
| `presidium` | Protocols, dataclasses, CEL policy engine, scoring library, trust scoring, `GovernedRuntime`, drop-in `ModelProvider`/`ToolProvider` adapters | `pip install presidium` | M1–M3 complete |
| `presidium-contrib` | Real network server (`presidium-contrib[server]`, M7), adapters for OPA/OpenBao/AgentGateway/Slack/Webhook/Postgres; reference impls for Agent Registry, MCP governance, trust scoring, service mode | `pip install presidium-contrib[opa]` | M1–M3 complete; M7 (Presidium Server) shipped |

`presidium` is the only required dependency. `presidium-contrib` extras are opt-in:

```
presidium-contrib[server]        # Presidium Server (M7) — check_grant() over real REST+mTLS
presidium-contrib[opa]           # OPA adapter (for teams already running OPA)
presidium-contrib[openbao]       # OpenBao credential backend (Vault-compatible, MPL 2.0)
presidium-contrib[agentgateway]  # AgentGateway (Linux Foundation) — reference LLM + MCP + A2A gateway
presidium-contrib[slack]         # Slack-based human-in-the-loop
presidium-contrib[webhook]       # Webhook-based approval provider
presidium-contrib[postgres]      # PostgreSQL agent registry backend
```

**Real, current gap, not hidden**: a `LLMGatewayBackend`/`ToolsGatewayBackend` *pluggable-vendor*
abstraction (letting AgentGateway/LiteLLM/etc. be swapped as interchangeable backends) is designed
(see [`docs/design/llm-gateway.md`](docs/design/llm-gateway.md) and
[`docs/design/mcp-gateway.md`](docs/design/mcp-gateway.md)) but not built — there is no
`presidium-contrib[litellm]` extra yet, despite earlier drafts of this README describing one.
Kong, Portkey, Cloudflare AI Gateway, Helicone, TrueFoundry are stubbed in the design docs only,
not built either. `AgentGatewayClient` (`presidium-contrib[agentgateway]`) is real today, LLM-side
only (no `list_tools`/`call_tool` yet).

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
