# Presidium

**The governed agent platform built on [Civitas](https://github.com/jerynmathew/python-civitas).**

Runtime + governance as one architecture. Not bolted on, not a sidecar, native.

---

> **Status:** Pre-alpha. Documentation-first phase. No code yet — design docs and RFCs are being written before implementation begins.

## What Is Presidium?

Presidium is a governance layer for AI agent systems, built natively on top of the [Civitas](https://github.com/jerynmathew/python-civitas) agent runtime. Where Civitas provides Erlang/OTP-style supervision trees, message passing, and transport abstraction, Presidium adds:

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
├── packages/            # Code packages (coming soon)
│   ├── presidium/       # Interface library (protocols, CEL engine)
│   └── presidium-contrib/  # Adapters + reference implementations
├── AGENTS.md            # AI assistant instructions
└── pyproject.toml       # Workspace config
```

## Packages (Planned)

| Package | Purpose | Install | Status |
|---|---|---|---|
| `presidium` | Protocols, dataclasses, CEL policy engine (default) | `pip install presidium` | Design |
| `presidium-contrib` | Adapters for OPA, Vault, LiteLLM Proxy, Slack HITL; reference impls for Agent Registry, MCP governance, trust scoring | `pip install presidium-contrib[opa]` | Design |

`presidium` is the only required dependency. `presidium-contrib` extras are opt-in:

```
presidium-contrib[opa]      # OPA adapter (for teams already running OPA)
presidium-contrib[vault]    # HashiCorp Vault credential backend
presidium-contrib[litellm]  # LiteLLM Proxy for LLM routing
presidium-contrib[slack]    # Slack-based human-in-the-loop
```

### Library Mode vs. Service Mode

Every component starts as a library. You import it, it runs in-process, evaluation takes microseconds. When you outgrow in-process (distributed deployments, multi-tenant isolation), some components can optionally deploy as a service. The interface stays the same either way.

### Policy Engine: CEL by Default

The default policy engine is [CEL (Common Expression Language)](https://cel.dev). CEL is embeddable as a library, evaluates in microseconds with no sidecar, and is already the policy language for Kubernetes admission webhooks and Google Cloud IAM. If you already run OPA infrastructure, `presidium-contrib[opa]` wraps it as an adapter.

### Where Presidium Builds vs. Wraps

Mature products exist for some components. Presidium wraps them:

| Component | Backend | How |
|---|---|---|
| Policy engine | CEL (default), OPA (adapter) | `presidium-contrib[opa]` |
| Credential management | HashiCorp Vault | `presidium-contrib[vault]` |
| LLM routing | LiteLLM Proxy | `presidium-contrib[litellm]` |
| Human-in-the-loop | Slack, Temporal | `presidium-contrib[slack]` |

For components where nothing mature exists, Presidium ships reference implementations in `presidium-contrib`:

| Component | Why a reference impl |
|---|---|
| Agent Registry with grants + trust scores | No existing product models agent identity this way |
| MCP governance gateway | MCP is new; no governance tooling exists yet |
| Trust scoring | Novel concept; no prior art to wrap |

## Relationship to Civitas

Civitas is the **runtime**. Presidium is the **governance layer**. They share the same org and philosophy but are separate projects. The package structure mirrors Civitas directly: `civitas` (protocols + defaults) and `civitas-contrib` (provider implementations) map to `presidium` and `presidium-contrib`.

- Civitas handles: supervision trees, message passing, transport, crash recovery, OTEL tracing
- Presidium handles: policy enforcement, agent identity, gateways, eval, compliance
- Together: the only platform where governance is architectural, not an afterthought

## License

[Apache License 2.0](LICENSE)

## Contributing

This project is in its documentation-first phase. Contributions to design docs and RFCs are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
