# Presidium

**The governed agent platform built on [Civitas](https://github.com/jerynmathew/python-civitas).**

Runtime + governance as one architecture — not bolted on, not a sidecar, native.

---

> **Status:** Pre-alpha. Documentation-first phase. No code yet — design docs and RFCs are being written before implementation begins.

## What Is Presidium?

Presidium is a governance layer for AI agent systems, built natively on top of the [Civitas](https://github.com/jerynmathew/python-civitas) agent runtime. Where Civitas provides Erlang/OTP-style supervision trees, message passing, and transport abstraction, Presidium adds:

- **Agent Registry** — identity, capabilities, trust tracking
- **Policy Engine** — declarative policies enforced as supervisor constraints
- **LLM Gateway** — rate limiting, cost tracking, model routing
- **MCP Gateway** — tool access governance, poisoning detection
- **Eval Framework** — governance-aware evaluation with external exporter support

## Why?

88% of AI agents fail to reach production ([TURION.AI, 2026](https://turion.ai/blog/state-of-ai-agents-enterprise-adoption-2026/)). The failures aren't model quality — they're infrastructure: no fault tolerance, no policy enforcement, no observability, no governance.

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
├── AGENTS.md            # AI assistant instructions
└── pyproject.toml       # Workspace config
```

## Packages (Planned)

| Package | Purpose | Status |
|---|---|---|
| `presidium-registry` | Agent identity, capability registration, trust tracking | 📋 Design |
| `presidium-policy` | Policy definition, evaluation, enforcement | 📋 Design |
| `presidium-llm-gateway` | LLM request routing, rate limiting, cost tracking | 📋 Design |
| `presidium-mcp-gateway` | Tool access governance, poisoning detection | 📋 Design |
| `presidium-eval` | Governance-aware evaluation, external exports | 📋 Design |
| `presidium-sdk` | Unified developer API (`pip install presidium`) | 📋 Design |

## Relationship to Civitas

Civitas is the **runtime**. Presidium is the **governance layer**. They share the same org and philosophy but are separate projects:

- Civitas handles: supervision trees, message passing, transport, crash recovery, OTEL tracing
- Presidium handles: policy enforcement, agent identity, gateways, eval, compliance
- Together: the only platform where governance is architectural, not an afterthought

## License

[Apache License 2.0](LICENSE)

## Contributing

This project is in its documentation-first phase. Contributions to design docs and RFCs are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md).
