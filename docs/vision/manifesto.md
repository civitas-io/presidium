# Presidium Manifesto

> Why Presidium exists and what it stands for.

## The Problem

AI agents are failing in production. Not because models are bad — because infrastructure is missing.

- **88% of AI agents fail to reach production** (TURION.AI, 2026)
- **40% of agentic AI projects will be canceled by 2027** (Gartner)
- **Only 2% of organizations have achieved scaled agent deployment** (RAYSolute, Q1 2026)
- **3-15% tool call failure rate per call** — in an 8-step workflow, 34% cumulative failure probability (Composio, 2025)

The root causes are engineering problems, not model limitations:

1. Silent tool call failures with no error boundaries
2. Cascading failures across agent systems
3. No retry or backoff mechanisms
4. State loss on crash
5. No step-level observability
6. No resource limits or backpressure
7. No policy enforcement — agents can do anything
8. No identity or trust tracking — agents are anonymous

## The Gap

The industry has two halves of a solution:

**Runtimes** (Temporal at $5B, Civitas, Inngest, Restate) solve reliability:
- Durable execution, fault tolerance, state persistence
- But they don't govern — any agent can do anything

**Governance tools** (Microsoft AGT, Fiddler at $100M) solve safety:
- Policy enforcement, guardrails, observability, compliance
- But they don't run agents — they're sidecars bolted onto whatever runtime exists

Nobody provides both. The runtime and the governance are built by different teams, from different companies, with different assumptions. The seams between them are where agents fail.

## The Thesis

**Governance should be architectural, not an afterthought.**

A policy isn't a sidecar — it's a supervisor constraint. An agent's identity isn't a DID certificate — it's a registry entry that determines what supervision tree it belongs to. Rate limiting isn't a proxy — it's a mailbox bound. Trust isn't a score computed externally — it's a runtime signal that affects restart strategies.

When governance and runtime are the same system, you don't have integration gaps. You don't have "the governance tool didn't catch it because the runtime didn't emit the right telemetry." You don't have agents that pass all policy checks but crash because nobody supervises them.

## The Principles

### 1. Open Source First

Apache 2.0. No BSL. No "open core with essential features behind a paywall." The governance layer that protects users should not be controlled by a single vendor. The core is free forever.

### 2. Python-Native

One language, done right. 80% of AI/ML work is Python. We don't split focus across TypeScript, Rust, Go, and C#. We make Python excellent.

### 3. Developer-Centric

`pip install presidium` → governed agent in 5 minutes. Not 9 packages to assemble. Not a cluster to deploy. Not a YAML schema to learn before writing code. Simple things should be simple; complex things should be possible.

### 4. Vendor-Neutral

No cloud lock-in. No LLM provider lock-in. No observability vendor lock-in. Presidium generates OTEL telemetry — you send it wherever you want: Fiddler, Arize, Langfuse, Datadog, Prometheus, or stdout.

### 5. Built on Proven Patterns

Civitas brings 30+ years of Erlang/OTP patterns. Supervision trees, actor model, message passing — these aren't experiments. They're battle-tested in telecom, finance, and distributed systems. Presidium extends these with governance primitives that feel native, not foreign.

### 6. Documentation-Driven

Design docs before code. RFCs for significant decisions. Every component has a written design that's reviewed before implementation begins. This isn't waterfall — it's discipline.

## The Name

**Presidium** (Latin: *praesidium*) — garrison, guard, protection. A body that governs and protects. In Roman governance, the presidium was the garrison that maintained order without ruling — it enabled civic function by providing security and structure.

That's what this project does: it doesn't tell agents what to think. It ensures they operate within bounds, recover from failures, and remain accountable.

## The Vision

The only agent platform where governance isn't an afterthought — it's the architecture.
