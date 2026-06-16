# RFC-003: Agent Value Chain — From Registry to Business Value

**Status:** Draft
**Author:** Jeryn Mathew
**Created:** 2026-06-16
**Milestone:** M4 (foundation), M5 (outcomes), M6 (feedback loop)

---

## Summary

This RFC proposes extending Presidium with an **Agent Value Chain** — a five-stage pipeline that connects agent identity to measurable business impact:

**Agent Registry → Agent View (topology) → Expected ROI → Runtime Costs → Actual Business Value**

The core insight: **value is not a metric to compute — it is a policy to enforce.** Every observability vendor measures cost after the fact. Presidium is the only layer that can *require* value declaration before an agent runs.

---

## Motivation

### The Measurement Crisis

The AI agent industry has a measurement problem:

- **95%** of AI pilots deliver zero measurable P&L impact (MIT 2026)
- **Only 25%** of AI initiatives deliver expected ROI (IBM CEO Study 2026)
- **Only 29%** of organizations can measure ROI confidently
- **61%** deploy AI with no baseline measurement beforehand
- **42%** of companies abandoned most AI projects in 2025 (S&P Global)
- Typical AI payback: **2–4 years**, not the 7–12 months enterprises expect
- Vendor ROI claims are typically **2–4× the realized number**

The root cause is structural, not technical: nobody requires measurement infrastructure before deployment.

<p align="center">

```svg
<svg viewBox="0 0 800 380" xmlns="http://www.w3.org/2000/svg" font-family="Inter, system-ui, sans-serif">
  <!-- Title -->
  <text x="400" y="30" text-anchor="middle" font-size="16" font-weight="700" fill="#1e293b">The Measurement Gap</text>

  <!-- Left: Broken loop (current state) -->
  <text x="200" y="65" text-anchor="middle" font-size="13" font-weight="600" fill="#dc2626">Current State (95% of deployments)</text>

  <rect x="80" y="80" width="240" height="40" rx="8" fill="#fef2f2" stroke="#dc2626" stroke-width="1.5"/>
  <text x="200" y="105" text-anchor="middle" font-size="12" fill="#991b1b">Deploy agents (no baseline)</text>

  <line x1="200" y1="120" x2="200" y2="140" stroke="#dc2626" stroke-width="1.5" marker-end="url(#arrowRed)"/>

  <rect x="80" y="140" width="240" height="40" rx="8" fill="#fef2f2" stroke="#dc2626" stroke-width="1.5"/>
  <text x="200" y="165" text-anchor="middle" font-size="12" fill="#991b1b">Costs accumulate (unattributed)</text>

  <line x1="200" y1="180" x2="200" y2="200" stroke="#dc2626" stroke-width="1.5" marker-end="url(#arrowRed)"/>

  <rect x="80" y="200" width="240" height="40" rx="8" fill="#fef2f2" stroke="#dc2626" stroke-width="1.5"/>
  <text x="200" y="225" text-anchor="middle" font-size="12" fill="#991b1b">CFO asks "what's the ROI?"</text>

  <line x1="200" y1="240" x2="200" y2="260" stroke="#dc2626" stroke-width="1.5" marker-end="url(#arrowRed)"/>

  <rect x="80" y="260" width="240" height="40" rx="8" fill="#fef2f2" stroke="#dc2626" stroke-width="1.5"/>
  <text x="200" y="285" text-anchor="middle" font-size="12" fill="#991b1b">No answer → budget cut</text>

  <line x1="130" y1="300" x2="70" y2="340" stroke="#dc2626" stroke-width="1.5" stroke-dasharray="5,5"/>
  <text x="60" y="355" font-size="11" fill="#dc2626">↻ Repeat</text>

  <!-- Right: Closed loop (with Presidium) -->
  <text x="600" y="65" text-anchor="middle" font-size="13" font-weight="600" fill="#16a34a">With Agent Value Chain</text>

  <rect x="480" y="80" width="240" height="40" rx="8" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5"/>
  <text x="600" y="100" text-anchor="middle" font-size="11" fill="#166534">Declare outcome + baseline</text>
  <text x="600" y="113" text-anchor="middle" font-size="10" fill="#166534" font-style="italic">(enforced at registration)</text>

  <line x1="600" y1="120" x2="600" y2="140" stroke="#16a34a" stroke-width="1.5" marker-end="url(#arrowGreen)"/>

  <rect x="480" y="140" width="240" height="40" rx="8" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5"/>
  <text x="600" y="165" text-anchor="middle" font-size="11" fill="#166534">Costs attributed per agent/task</text>

  <line x1="600" y1="180" x2="600" y2="200" stroke="#16a34a" stroke-width="1.5" marker-end="url(#arrowGreen)"/>

  <rect x="480" y="200" width="240" height="40" rx="8" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5"/>
  <text x="600" y="225" text-anchor="middle" font-size="11" fill="#166534">Value captured on success (POST_TOOL)</text>

  <line x1="600" y1="240" x2="600" y2="260" stroke="#16a34a" stroke-width="1.5" marker-end="url(#arrowGreen)"/>

  <rect x="480" y="260" width="240" height="40" rx="8" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5"/>
  <text x="600" y="280" text-anchor="middle" font-size="11" fill="#166534">ROI = (Value − Cost) / Cost</text>
  <text x="600" y="293" text-anchor="middle" font-size="10" fill="#166534" font-style="italic">replayable via ScoringSpec</text>

  <line x1="720" y1="280" x2="740" y2="280" stroke="#16a34a" stroke-width="1.5"/>
  <line x1="740" y1="280" x2="740" y2="100" stroke="#16a34a" stroke-width="1.5"/>
  <line x1="740" y1="100" x2="720" y2="100" stroke="#16a34a" stroke-width="1.5" marker-end="url(#arrowGreen)"/>
  <text x="755" y="195" text-anchor="start" font-size="10" fill="#16a34a" transform="rotate(90, 755, 195)">Trust feedback</text>

  <!-- Arrow markers -->
  <defs>
    <marker id="arrowRed" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6" fill="#dc2626"/>
    </marker>
    <marker id="arrowGreen" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6" fill="#16a34a"/>
    </marker>
  </defs>
</svg>
```

</p>

### Why This Matters for Presidium

Presidium already governs *how* agents behave (policy, grants, trust). The missing dimension is *whether agents are worth running*. Trust says an agent behaves well. Value says an agent delivers business impact. Both are governance decisions — not dashboard features.

Presidium sits at the only junction that sees both:
- **Pre-execution intent** — what the agent is declared to do (outcome binding)
- **Post-execution reality** — what actually happened (cost + value events)

No observability platform can enforce baseline declaration. No FinOps tool can tie cost to business outcomes through a governance policy. Presidium can.

---

## The Problem-Solution Space

### Problem 1: "We deployed 50 agents. What's the ROI?"

**Current state:** Organizations deploy agents, track token costs in Langfuse, and have no way to connect those costs to business outcomes. CFO asks for ROI → engineering says "productivity improved" → CFO says "show me the P&L impact" → silence.

**Solution:** `OutcomeBinding` declares what each agent (or agent workflow) is supposed to produce. `ValueBaseline` captures the "before" number. `CostLedger` captures runtime spend. `ValueLedger` captures successful outcomes. ROI is computed by the scoring library — pinned, replayable, auditable.

```
$ presidium roi show --agent researcher --window 90d

Agent: presidium://acme.com/prod/researcher
Outcome: vendor-approval (declared 2026-03-15)
Baseline: $45/approval (manual, N=50, Q4 2025)

  Period          Cost        Value    Approvals   Cost/Unit    ROI
  ─────────────   ─────────   ──────   ─────────   ─────────   ─────
  2026-Q1         $2,340      $8,100   180         $13.00      246%
  2026-Q2 (MTD)   $1,890      $6,750   150         $12.60      257%

  Spec: sha256:a4f2c8... (pinned, replayable)
```

### Problem 2: "Which agents in this workflow are pulling their weight?"

**Current state:** A multi-agent workflow completes tasks but it's unclear which agents contribute value vs. which are overhead. A research agent, synthesis agent, and review agent collaborate — the research agent makes 80% of the LLM calls but the review agent catches 30% of errors.

**Solution:** `workflow.trace_id` propagated through audit events gives the tree view. Cost attribution per agent within the trace shows the spend distribution. Value capture at the workflow outcome ties back to the trace. The "forest" view aggregates across traces by root agent.

<p align="center">

```svg
<svg viewBox="0 0 800 420" xmlns="http://www.w3.org/2000/svg" font-family="Inter, system-ui, sans-serif">
  <!-- Title -->
  <text x="400" y="28" text-anchor="middle" font-size="16" font-weight="700" fill="#1e293b">Topology Derived from Trace Context</text>
  <text x="400" y="48" text-anchor="middle" font-size="11" fill="#64748b">No graph database — group audit events by trace_id (tree) or root agent_id (forest)</text>

  <!-- Tree View (left) -->
  <text x="210" y="80" text-anchor="middle" font-size="13" font-weight="600" fill="#2563eb">Tree View (single trace)</text>

  <!-- Orchestrator -->
  <rect x="130" y="95" width="160" height="36" rx="6" fill="#eff6ff" stroke="#2563eb" stroke-width="1.5"/>
  <text x="210" y="113" text-anchor="middle" font-size="11" fill="#1e40af">orchestrator</text>
  <text x="210" y="125" text-anchor="middle" font-size="9" fill="#3b82f6">trace: abc-123</text>

  <!-- Lines to children -->
  <line x1="170" y1="131" x2="120" y2="155" stroke="#93c5fd" stroke-width="1.5"/>
  <line x1="210" y1="131" x2="210" y2="155" stroke="#93c5fd" stroke-width="1.5"/>
  <line x1="250" y1="131" x2="300" y2="155" stroke="#93c5fd" stroke-width="1.5"/>

  <!-- Research Agent -->
  <rect x="40" y="155" width="160" height="48" rx="6" fill="#eff6ff" stroke="#2563eb" stroke-width="1.2"/>
  <text x="120" y="173" text-anchor="middle" font-size="11" fill="#1e40af">researcher</text>
  <text x="120" y="186" text-anchor="middle" font-size="9" fill="#64748b">$18.40 (80% of cost)</text>
  <text x="120" y="197" text-anchor="middle" font-size="9" fill="#64748b">45 LLM calls</text>

  <!-- Synthesis Agent -->
  <rect x="130" y="155" width="160" height="48" rx="6" fill="#eff6ff" stroke="#2563eb" stroke-width="1.2"/>
  <text x="210" y="173" text-anchor="middle" font-size="11" fill="#1e40af">synthesizer</text>
  <text x="210" y="186" text-anchor="middle" font-size="9" fill="#64748b">$2.10 (9% of cost)</text>
  <text x="210" y="197" text-anchor="middle" font-size="9" fill="#64748b">3 LLM calls</text>

  <!-- Review Agent -->
  <rect x="220" y="155" width="160" height="48" rx="6" fill="#eff6ff" stroke="#2563eb" stroke-width="1.2"/>
  <text x="300" y="173" text-anchor="middle" font-size="11" fill="#1e40af">reviewer</text>
  <text x="300" y="186" text-anchor="middle" font-size="9" fill="#64748b">$2.50 (11% of cost)</text>
  <text x="300" y="197" text-anchor="middle" font-size="9" fill="#64748b">caught 30% of errors</text>

  <!-- Outcome -->
  <rect x="100" y="225" width="220" height="32" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5"/>
  <text x="210" y="246" text-anchor="middle" font-size="11" fill="#166534">Outcome: vendor-approved → $45 value</text>

  <!-- Forest View (right) -->
  <text x="600" y="80" text-anchor="middle" font-size="13" font-weight="600" fill="#7c3aed">Forest View (across traces)</text>

  <!-- Tree 1 -->
  <rect x="480" y="95" width="100" height="28" rx="5" fill="#f5f3ff" stroke="#7c3aed" stroke-width="1.2"/>
  <text x="530" y="113" text-anchor="middle" font-size="10" fill="#5b21b6">orchestrator</text>
  <line x1="510" y1="123" x2="500" y2="140" stroke="#c4b5fd" stroke-width="1"/>
  <line x1="530" y1="123" x2="530" y2="140" stroke="#c4b5fd" stroke-width="1"/>
  <line x1="550" y1="123" x2="560" y2="140" stroke="#c4b5fd" stroke-width="1"/>
  <rect x="475" y="140" width="50" height="20" rx="4" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="0.8"/>
  <text x="500" y="154" text-anchor="middle" font-size="8" fill="#7c3aed">res</text>
  <rect x="505" y="140" width="50" height="20" rx="4" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="0.8"/>
  <text x="530" y="154" text-anchor="middle" font-size="8" fill="#7c3aed">syn</text>
  <rect x="535" y="140" width="50" height="20" rx="4" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="0.8"/>
  <text x="560" y="154" text-anchor="middle" font-size="8" fill="#7c3aed">rev</text>
  <text x="530" y="175" text-anchor="middle" font-size="9" fill="#64748b">trace-001: $23 → $45</text>

  <!-- Tree 2 -->
  <rect x="630" y="95" width="100" height="28" rx="5" fill="#f5f3ff" stroke="#7c3aed" stroke-width="1.2"/>
  <text x="680" y="113" text-anchor="middle" font-size="10" fill="#5b21b6">orchestrator</text>
  <line x1="660" y1="123" x2="650" y2="140" stroke="#c4b5fd" stroke-width="1"/>
  <line x1="680" y1="123" x2="680" y2="140" stroke="#c4b5fd" stroke-width="1"/>
  <line x1="700" y1="123" x2="710" y2="140" stroke="#c4b5fd" stroke-width="1"/>
  <rect x="625" y="140" width="50" height="20" rx="4" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="0.8"/>
  <text x="650" y="154" text-anchor="middle" font-size="8" fill="#7c3aed">res</text>
  <rect x="655" y="140" width="50" height="20" rx="4" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="0.8"/>
  <text x="680" y="154" text-anchor="middle" font-size="8" fill="#7c3aed">syn</text>
  <rect x="685" y="140" width="50" height="20" rx="4" fill="#f5f3ff" stroke="#c4b5fd" stroke-width="0.8"/>
  <text x="710" y="154" text-anchor="middle" font-size="8" fill="#7c3aed">rev</text>
  <text x="680" y="175" text-anchor="middle" font-size="9" fill="#64748b">trace-002: $19 → $45</text>

  <!-- Aggregation -->
  <rect x="500" y="200" width="200" height="56" rx="6" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.5"/>
  <text x="600" y="220" text-anchor="middle" font-size="11" font-weight="600" fill="#5b21b6">Forest Aggregate</text>
  <text x="600" y="235" text-anchor="middle" font-size="10" fill="#64748b">150 traces, $3,150 cost</text>
  <text x="600" y="248" text-anchor="middle" font-size="10" fill="#64748b">$6,750 value → 114% ROI</text>

  <!-- Key -->
  <rect x="40" y="290" width="720" height="115" rx="8" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1"/>
  <text x="60" y="312" font-size="12" font-weight="600" fill="#334155">How It Works</text>
  <text x="60" y="332" font-size="11" fill="#475569">1. Every audit event carries workflow.trace_id + workflow.span_id (OTel propagation)</text>
  <text x="60" y="350" font-size="11" fill="#475569">2. Tree view: GROUP BY trace_id → reconstruct parent-child from span hierarchy</text>
  <text x="60" y="368" font-size="11" fill="#475569">3. Forest view: GROUP BY root agent_id across all traces → aggregate cost/value</text>
  <text x="60" y="386" font-size="11" fill="#475569">4. No graph database, no workflow DAG extraction — derived from the audit stream</text>
</svg>
```

</p>

### Problem 3: "Agent costs spiked 300% this month — why?"

**Current state:** Token costs visible in Langfuse but not attributed to business outcomes. A research agent tripled its cost because it handles 3× more vendor approvals — that's a feature, not a bug. But without outcome binding, the cost spike looks like waste.

**Solution:** `CostLedger` attributes cost per agent, per task, per tenant, per workflow trace. When paired with `ValueLedger`, the cost spike maps to a proportional value increase → ROI stays stable. Without value context, the same data triggers a false alarm.

### Problem 4: "How do we justify the AI investment to the board?"

**Current state:** Engineering builds agents. Finance asks for returns. The two worlds speak different languages (tokens vs. dollars, latency vs. cycle time).

**Solution:** `ValueBaseline` speaks finance's language — declared in dollars, measured against a pre-pilot "before" number, with a locked `spec_hash` for tamper-evidence. The ROI computation reuses `presidium.scoring.windowed_score` — the same engine that computes trust scores, applied to value. Deterministic replay means the CFO's auditor can reproduce the number.

---

## Architecture

### Five-Stage Pipeline

<p align="center">

```svg
<svg viewBox="0 0 820 500" xmlns="http://www.w3.org/2000/svg" font-family="Inter, system-ui, sans-serif">
  <!-- Title -->
  <text x="410" y="28" text-anchor="middle" font-size="16" font-weight="700" fill="#1e293b">Agent Value Chain — Five Stages</text>

  <!-- Stage 1: Registry (existing) -->
  <rect x="30" y="60" width="150" height="80" rx="8" fill="#eff6ff" stroke="#2563eb" stroke-width="2"/>
  <text x="105" y="85" text-anchor="middle" font-size="12" font-weight="600" fill="#1e40af">Stage 1</text>
  <text x="105" y="100" text-anchor="middle" font-size="11" fill="#1e40af">Agent Registry</text>
  <text x="105" y="115" text-anchor="middle" font-size="9" fill="#3b82f6">Identity · Grants</text>
  <text x="105" y="127" text-anchor="middle" font-size="9" fill="#3b82f6">Trust · Status</text>
  <text x="105" y="150" text-anchor="middle" font-size="9" font-weight="600" fill="#2563eb">EXISTS (M2)</text>

  <line x1="180" y1="100" x2="210" y2="100" stroke="#94a3b8" stroke-width="1.5" marker-end="url(#arrowGray)"/>

  <!-- Stage 2: View (new, derived) -->
  <rect x="210" y="60" width="150" height="80" rx="8" fill="#f0fdf4" stroke="#16a34a" stroke-width="2"/>
  <text x="285" y="85" text-anchor="middle" font-size="12" font-weight="600" fill="#166534">Stage 2</text>
  <text x="285" y="100" text-anchor="middle" font-size="11" fill="#166534">Agent View</text>
  <text x="285" y="115" text-anchor="middle" font-size="9" fill="#16a34a">Tree · Forest</text>
  <text x="285" y="127" text-anchor="middle" font-size="9" fill="#16a34a">trace_id derivation</text>
  <text x="285" y="150" text-anchor="middle" font-size="9" font-weight="600" fill="#16a34a">NEW (M4)</text>

  <line x1="360" y1="100" x2="390" y2="100" stroke="#94a3b8" stroke-width="1.5" marker-end="url(#arrowGray)"/>

  <!-- Stage 3: Expected ROI (new) -->
  <rect x="390" y="60" width="150" height="80" rx="8" fill="#f0fdf4" stroke="#16a34a" stroke-width="2"/>
  <text x="465" y="85" text-anchor="middle" font-size="12" font-weight="600" fill="#166534">Stage 3</text>
  <text x="465" y="100" text-anchor="middle" font-size="11" fill="#166534">Expected ROI</text>
  <text x="465" y="115" text-anchor="middle" font-size="9" fill="#16a34a">OutcomeBinding</text>
  <text x="465" y="127" text-anchor="middle" font-size="9" fill="#16a34a">ValueBaseline</text>
  <text x="465" y="150" text-anchor="middle" font-size="9" font-weight="600" fill="#16a34a">NEW (M5)</text>

  <line x1="540" y1="100" x2="570" y2="100" stroke="#94a3b8" stroke-width="1.5" marker-end="url(#arrowGray)"/>

  <!-- Stage 4: Costs (new) -->
  <rect x="570" y="60" width="150" height="80" rx="8" fill="#f0fdf4" stroke="#16a34a" stroke-width="2"/>
  <text x="645" y="85" text-anchor="middle" font-size="12" font-weight="600" fill="#166534">Stage 4</text>
  <text x="645" y="100" text-anchor="middle" font-size="11" fill="#166534">Runtime Costs</text>
  <text x="645" y="115" text-anchor="middle" font-size="9" fill="#16a34a">CostLedger</text>
  <text x="645" y="127" text-anchor="middle" font-size="9" fill="#16a34a">per-agent attribution</text>
  <text x="645" y="150" text-anchor="middle" font-size="9" font-weight="600" fill="#16a34a">NEW (M4)</text>

  <!-- Stage 5: Value (new) -->
  <rect x="390" y="185" width="330" height="70" rx="8" fill="#faf5ff" stroke="#7c3aed" stroke-width="2"/>
  <text x="555" y="210" text-anchor="middle" font-size="12" font-weight="600" fill="#5b21b6">Stage 5: Actual Business Value</text>
  <text x="555" y="228" text-anchor="middle" font-size="11" fill="#7c3aed">ValueLedger · ROI = (Value − Cost) / Cost</text>
  <text x="555" y="245" text-anchor="middle" font-size="9" fill="#7c3aed">spec-hashed, replayable, auditable</text>
  <text x="555" y="262" text-anchor="middle" font-size="9" font-weight="600" fill="#7c3aed">NEW (M5)</text>

  <!-- Arrows from cost/outcome to value -->
  <line x1="645" y1="140" x2="645" y2="185" stroke="#7c3aed" stroke-width="1.5" marker-end="url(#arrowPurple)"/>
  <line x1="465" y1="140" x2="465" y2="185" stroke="#7c3aed" stroke-width="1.5" marker-end="url(#arrowPurple)"/>

  <!-- Backbone -->
  <rect x="30" y="300" width="760" height="50" rx="8" fill="#f8fafc" stroke="#64748b" stroke-width="1.5" stroke-dasharray="6,3"/>
  <text x="410" y="322" text-anchor="middle" font-size="12" font-weight="600" fill="#475569">Backbone: presidium.scoring (Event · ScoringSpec · windowed_score · replay)</text>
  <text x="410" y="338" text-anchor="middle" font-size="10" fill="#64748b">Same library used for trust, evals, budget, compliance — value is the fifth consumer</text>

  <!-- Connections to backbone -->
  <line x1="105" y1="140" x2="105" y2="300" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4,4"/>
  <line x1="285" y1="140" x2="285" y2="300" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4,4"/>
  <line x1="555" y1="255" x2="555" y2="300" stroke="#94a3b8" stroke-width="1" stroke-dasharray="4,4"/>

  <!-- Enforcement layer -->
  <rect x="30" y="370" width="760" height="50" rx="8" fill="#fef2f2" stroke="#dc2626" stroke-width="1.5"/>
  <text x="410" y="392" text-anchor="middle" font-size="12" font-weight="600" fill="#991b1b">Enforcement: CelPolicyEngine</text>
  <text x="410" y="408" text-anchor="middle" font-size="10" fill="#b91c1c">REGISTRATION: require OutcomeBinding + Baseline · POST_TOOL: capture value on success</text>

  <!-- Feedback arrow -->
  <path d="M 740 370 Q 780 280 740 185" fill="none" stroke="#7c3aed" stroke-width="1.5" stroke-dasharray="5,3" marker-end="url(#arrowPurple)"/>
  <text x="775" y="280" text-anchor="start" font-size="9" fill="#7c3aed">ROI → Trust</text>
  <text x="775" y="292" text-anchor="start" font-size="9" fill="#7c3aed">feedback</text>

  <!-- Arrow markers -->
  <defs>
    <marker id="arrowGray" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6" fill="#94a3b8"/>
    </marker>
    <marker id="arrowPurple" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6" fill="#7c3aed"/>
    </marker>
  </defs>

  <!-- Legend -->
  <rect x="30" y="440" width="16" height="12" rx="3" fill="#eff6ff" stroke="#2563eb" stroke-width="1"/>
  <text x="52" y="450" font-size="10" fill="#475569">Existing (M2)</text>
  <rect x="150" y="440" width="16" height="12" rx="3" fill="#f0fdf4" stroke="#16a34a" stroke-width="1"/>
  <text x="172" y="450" font-size="10" fill="#475569">New addition</text>
  <rect x="270" y="440" width="16" height="12" rx="3" fill="#faf5ff" stroke="#7c3aed" stroke-width="1"/>
  <text x="292" y="450" font-size="10" fill="#475569">Value layer</text>
</svg>
```

</p>

### Presidium's Unique Position

<p align="center">

```svg
<svg viewBox="0 0 800 360" xmlns="http://www.w3.org/2000/svg" font-family="Inter, system-ui, sans-serif">
  <!-- Title -->
  <text x="400" y="28" text-anchor="middle" font-size="16" font-weight="700" fill="#1e293b">Value as Policy, Not Dashboard</text>

  <!-- Left: Observability approach -->
  <text x="200" y="60" text-anchor="middle" font-size="13" font-weight="600" fill="#94a3b8">Observability Approach (Langfuse, Fiddler)</text>

  <rect x="60" y="80" width="280" height="36" rx="6" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2"/>
  <text x="200" y="103" text-anchor="middle" font-size="11" fill="#64748b">Agent deployed (no requirements)</text>

  <line x1="200" y1="116" x2="200" y2="130" stroke="#cbd5e1" stroke-width="1.2" marker-end="url(#arrowLightGray)"/>

  <rect x="60" y="130" width="280" height="36" rx="6" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2"/>
  <text x="200" y="153" text-anchor="middle" font-size="11" fill="#64748b">Events collected passively</text>

  <line x1="200" y1="166" x2="200" y2="180" stroke="#cbd5e1" stroke-width="1.2" marker-end="url(#arrowLightGray)"/>

  <rect x="60" y="180" width="280" height="36" rx="6" fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.2"/>
  <text x="200" y="203" text-anchor="middle" font-size="11" fill="#64748b">Dashboards show cost trends</text>

  <line x1="200" y1="216" x2="200" y2="230" stroke="#cbd5e1" stroke-width="1.2" marker-end="url(#arrowLightGray)"/>

  <rect x="60" y="230" width="280" height="36" rx="6" fill="#fff7ed" stroke="#f59e0b" stroke-width="1.5"/>
  <text x="200" y="253" text-anchor="middle" font-size="11" fill="#92400e">❓ No baseline → ROI unknowable</text>

  <!-- Right: Governance approach -->
  <text x="600" y="60" text-anchor="middle" font-size="13" font-weight="600" fill="#16a34a">Governance Approach (Presidium)</text>

  <rect x="460" y="80" width="280" height="36" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5"/>
  <text x="600" y="98" text-anchor="middle" font-size="11" fill="#166534">REGISTRATION policy enforces:</text>
  <text x="600" y="110" text-anchor="middle" font-size="9" fill="#16a34a" font-style="italic">OutcomeBinding + ValueBaseline required</text>

  <line x1="600" y1="116" x2="600" y2="130" stroke="#16a34a" stroke-width="1.2" marker-end="url(#arrowDarkGreen)"/>

  <rect x="460" y="130" width="280" height="36" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5"/>
  <text x="600" y="153" text-anchor="middle" font-size="11" fill="#166534">Cost + value captured at policy hooks</text>

  <line x1="600" y1="166" x2="600" y2="180" stroke="#16a34a" stroke-width="1.2" marker-end="url(#arrowDarkGreen)"/>

  <rect x="460" y="180" width="280" height="36" rx="6" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5"/>
  <text x="600" y="198" text-anchor="middle" font-size="11" fill="#166534">ROI computed via scoring library</text>
  <text x="600" y="210" text-anchor="middle" font-size="9" fill="#16a34a" font-style="italic">spec-hashed, replayable</text>

  <line x1="600" y1="216" x2="600" y2="230" stroke="#16a34a" stroke-width="1.2" marker-end="url(#arrowDarkGreen)"/>

  <rect x="460" y="230" width="280" height="36" rx="6" fill="#ecfdf5" stroke="#059669" stroke-width="1.5"/>
  <text x="600" y="253" text-anchor="middle" font-size="11" fill="#065f46">✓ CFO-grade: baseline → actual → delta</text>

  <!-- Divider -->
  <line x1="400" y1="70" x2="400" y2="280" stroke="#e2e8f0" stroke-width="1" stroke-dasharray="4,4"/>

  <!-- Bottom callout -->
  <rect x="100" y="295" width="600" height="50" rx="8" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.5"/>
  <text x="400" y="317" text-anchor="middle" font-size="12" font-weight="600" fill="#5b21b6">The difference: enforcement, not observation</text>
  <text x="400" y="335" text-anchor="middle" font-size="11" fill="#6d28d9">Observability says "here's what happened." Governance says "you can't start without declaring what should happen."</text>

  <!-- Arrow markers -->
  <defs>
    <marker id="arrowLightGray" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6" fill="#cbd5e1"/>
    </marker>
    <marker id="arrowDarkGreen" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6" fill="#16a34a"/>
    </marker>
  </defs>
</svg>
```

</p>

---

## Data Model

### New Types (additions to Presidium)

```python
# presidium.value.model

@dataclass(frozen=True)
class OutcomeBinding:
    """The contract: 'this agent's job is to produce outcome X.'

    Declared at registration or workflow start. Audit-pinned via spec_hash.
    Required by REGISTRATION policy in production environments.
    """
    outcome_id: str                    # "vendor-approved", "incident-resolved"
    agent_id: str                      # presidium:// URI of the chain root
    workflow_trace_id: str | None      # OTel trace ID; None for static bindings
    declared_at: datetime
    declared_value_usd: float | None   # expected $ per success
    success_criteria: str              # CEL expression evaluated against POST_TOOL result
    owner: str                         # human sponsor (matches AgentRecord.owner)


@dataclass(frozen=True)
class ValueBaseline:
    """Pre-pilot 'before' number. Spec-hashed for tamper-evidence.

    The minimum viable CFO artifact: what did this process cost before
    the agent existed? How was that measured?
    """
    outcome_id: str
    methodology: str                   # "manual sample N=50, Q3 2025"
    baseline_value_per_unit_usd: float # cost per unit before automation
    baseline_cost_per_unit_usd: float  # what the human process cost
    baseline_quality: float            # 0.0–1.0
    sample_size: int
    measurement_window_days: int
    declared_by: str                   # human who signed off
    declared_at: datetime
    spec_hash: str                     # SHA-256 of canonical JSON
```

### Event Conventions (typed over `scoring.Event`)

Cost and value events are **not new dataclasses** — they are tag conventions over the existing `scoring.Event` schema. The scoring library already supports arbitrary tags and values. This avoids creating a parallel event system.

```python
# CostEvent convention (emitted by GovernedModelProvider, GovernedToolProvider)
Event(
    id="...",
    timestamp=now,
    tags={
        "type": "cost",
        "agent_id": "presidium://acme.com/prod/researcher",
        "workflow.trace_id": "abc-123",
        "tenant_id": "acme",
        "token_layer": "prompt",          # prompt | tool | memory | response
        "provider": "anthropic",
        "model": "claude-sonnet-4",
    },
    values={
        "cost_usd": 0.045,
        "tokens": 1500,
        "latency_ms": 230.0,
    },
)

# ValueEvent convention (emitted when success_criteria evaluates true)
Event(
    id="...",
    timestamp=now,
    tags={
        "type": "value",
        "outcome_id": "vendor-approved",
        "agent_id": "presidium://acme.com/prod/researcher",
        "workflow.trace_id": "abc-123",
        "tenant_id": "acme",
    },
    values={
        "value_usd": 45.0,
        "quality_score": 0.92,
        "duration_seconds": 340.0,
    },
)
```

### Protocols

```python
class CostLedger(Protocol):
    """Records and queries cost events attributed to agents."""
    async def record(self, event: Event) -> None: ...
    async def query(
        self,
        *,
        agent_id: str | None = None,
        workflow_trace_id: str | None = None,
        tenant_id: str | None = None,
        window: WindowConfig | None = None,
    ) -> list[Event]: ...

class ValueLedger(Protocol):
    """Records and queries value events tied to outcome bindings."""
    async def record(self, event: Event) -> None: ...
    async def query(self, **kw: Any) -> list[Event]: ...

class OutcomeRegistry(Protocol):
    """Stores and resolves outcome bindings for agents and workflows."""
    async def declare(self, binding: OutcomeBinding) -> None: ...
    async def resolve(self, workflow_trace_id: str) -> OutcomeBinding | None: ...
    async def list_for_agent(self, agent_id: str) -> list[OutcomeBinding]: ...

class BaselineStore(Protocol):
    """Stores pre-pilot baselines, spec-hashed for audit."""
    async def set(self, baseline: ValueBaseline) -> None: ...
    async def get(self, outcome_id: str) -> ValueBaseline | None: ...
```

---

## The Cost-Value Feedback Loop

<p align="center">

```svg
<svg viewBox="0 0 800 400" xmlns="http://www.w3.org/2000/svg" font-family="Inter, system-ui, sans-serif">
  <!-- Title -->
  <text x="400" y="28" text-anchor="middle" font-size="16" font-weight="700" fill="#1e293b">Cost-Value Feedback Loop</text>
  <text x="400" y="46" text-anchor="middle" font-size="11" fill="#64748b">Reuses existing trust scoring, policy engine, and scoring library</text>

  <!-- Agent acts -->
  <rect x="30" y="75" width="140" height="50" rx="8" fill="#eff6ff" stroke="#2563eb" stroke-width="1.5"/>
  <text x="100" y="97" text-anchor="middle" font-size="11" font-weight="600" fill="#1e40af">Agent acts</text>
  <text x="100" y="112" text-anchor="middle" font-size="9" fill="#3b82f6">LLM call / tool call</text>

  <line x1="170" y1="100" x2="210" y2="100" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrowMid)"/>

  <!-- Cost recorded -->
  <rect x="210" y="75" width="140" height="50" rx="8" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5"/>
  <text x="280" y="97" text-anchor="middle" font-size="11" font-weight="600" fill="#166534">Cost recorded</text>
  <text x="280" y="112" text-anchor="middle" font-size="9" fill="#16a34a">CostLedger.record()</text>

  <line x1="350" y1="100" x2="390" y2="100" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrowMid)"/>

  <!-- Outcome evaluated -->
  <rect x="390" y="75" width="160" height="50" rx="8" fill="#f0fdf4" stroke="#16a34a" stroke-width="1.5"/>
  <text x="470" y="92" text-anchor="middle" font-size="11" font-weight="600" fill="#166534">Outcome evaluated</text>
  <text x="470" y="107" text-anchor="middle" font-size="9" fill="#16a34a">POST_TOOL CEL policy</text>
  <text x="470" y="119" text-anchor="middle" font-size="9" fill="#16a34a">success_criteria check</text>

  <line x1="550" y1="100" x2="590" y2="100" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrowMid)"/>

  <!-- Value recorded -->
  <rect x="590" y="75" width="160" height="50" rx="8" fill="#faf5ff" stroke="#7c3aed" stroke-width="1.5"/>
  <text x="670" y="97" text-anchor="middle" font-size="11" font-weight="600" fill="#5b21b6">Value recorded</text>
  <text x="670" y="112" text-anchor="middle" font-size="9" fill="#7c3aed">ValueLedger.record()</text>

  <!-- Down to ROI -->
  <line x1="670" y1="125" x2="670" y2="165" stroke="#7c3aed" stroke-width="1.5" marker-end="url(#arrowPurpleMid)"/>

  <!-- ROI computed -->
  <rect x="530" y="165" width="280" height="55" rx="8" fill="#faf5ff" stroke="#7c3aed" stroke-width="2"/>
  <text x="670" y="188" text-anchor="middle" font-size="12" font-weight="600" fill="#5b21b6">ROI computed</text>
  <text x="670" y="205" text-anchor="middle" font-size="10" fill="#7c3aed">scoring.windowed_score(cost_events + value_events)</text>
  <text x="670" y="215" text-anchor="middle" font-size="9" fill="#7c3aed">spec-hashed · replayable · auditable</text>

  <!-- Down to trust -->
  <line x1="670" y1="220" x2="670" y2="260" stroke="#7c3aed" stroke-width="1.5" marker-end="url(#arrowPurpleMid)"/>

  <!-- Trust adjusted -->
  <rect x="530" y="260" width="280" height="50" rx="8" fill="#eff6ff" stroke="#2563eb" stroke-width="1.5"/>
  <text x="670" y="282" text-anchor="middle" font-size="11" font-weight="600" fill="#1e40af">Trust adjusted (M6)</text>
  <text x="670" y="297" text-anchor="middle" font-size="9" fill="#3b82f6">ROI as dimension in MultiDimensionalTrustScorer</text>

  <!-- Left arrow back up -->
  <line x1="530" y1="285" x2="100" y2="285" stroke="#2563eb" stroke-width="1.2" stroke-dasharray="5,3"/>
  <line x1="100" y1="285" x2="100" y2="130" stroke="#2563eb" stroke-width="1.2" stroke-dasharray="5,3" marker-end="url(#arrowBlueMid)"/>
  <text x="315" y="278" text-anchor="middle" font-size="10" fill="#2563eb">Autonomy gates updated → agent capabilities change</text>

  <!-- Bottom: what's reused -->
  <rect x="30" y="335" width="740" height="50" rx="8" fill="#f8fafc" stroke="#e2e8f0" stroke-width="1"/>
  <text x="400" y="355" text-anchor="middle" font-size="11" font-weight="600" fill="#475569">Components reused from existing Presidium</text>
  <text x="400" y="372" text-anchor="middle" font-size="10" fill="#64748b">scoring.Event · scoring.windowed_score · ScoringSpec · CelPolicyEngine · AuditEnricher · TrustScorer</text>

  <!-- Arrow markers -->
  <defs>
    <marker id="arrowMid" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6" fill="#64748b"/>
    </marker>
    <marker id="arrowPurpleMid" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6" fill="#7c3aed"/>
    </marker>
    <marker id="arrowBlueMid" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
      <path d="M0,0 L8,3 L0,6" fill="#2563eb"/>
    </marker>
  </defs>
</svg>
```

</p>

---

## Build vs. Integrate

| Presidium OWNS | Ecosystem handles |
|---|---|
| `OutcomeBinding` + `ValueBaseline` declaration and registration-time enforcement | Cost dashboards (Langfuse, Arize, Fiddler) |
| `CostLedger` / `ValueLedger` as `scoring.Event` streams tied to identity + grants + policies | Quality dashboards and anomaly detection |
| `ScoringSpec` for ROI formula — pinned, replayable, audit-evident | Trace topology visualization (Jaeger, Tempo, Honeycomb) |
| `workflow.trace_id` propagation through audit events | Cross-framework workflow extraction (Agentproof) |
| Trust-feedback loop: ROI → trust dimension → autonomy gate | Industry-specific ROI formulas |

### Explicitly NOT building

- **Dashboards or web UI** — Langfuse/Fiddler/Arize already own this surface
- **Shapley / LOO attribution math** — research-grade; emit data, let academics run it
- **Pricing tables or token counters** — AgentGateway + provider APIs handle this
- **Cross-framework workflow extraction** — Agentproof's job; receive trace IDs only
- **Real-time anomaly detection** — Langfuse already identifies 40x-median tenants
- **Pre-baked ROI formulas** — users declare via `ScoringSpec`; Presidium doesn't prescribe formulas

---

## Milestone Mapping

| Component | Milestone | Effort | What lands |
|---|---|---|---|
| `workflow.trace_id` / `span_id` in AuditEvent | **M4** | ~2 days | Every audit event carries trace context for topology derivation |
| `CostLedger` Protocol + `InMemoryCostLedger` | **M4** | ~3 days | Emit cost events from `GovernedModelProvider` with per-agent/task/tenant tags |
| `OutcomeRegistry` + `OutcomeBinding` + `BaselineStore` + `ValueBaseline` | **M5** | ~2 days | Declare what agents are supposed to produce and what the "before" looked like |
| `ValueLedger` + POST_TOOL value capture | **M5** | ~2 days | Emit value events when `success_criteria` CEL expression evaluates true |
| `presidium roi show <agent>` CLI | **M5** | ~1 day | Reuse `scoring.windowed_score` over joined cost + value streams |
| Default `require-outcome-binding` registration policy | **M5** | ~1 day | Optional in dev, hard-enforced in prod via existing `EnforcementMode` |
| ROI as trust dimension in `MultiDimensionalTrustScorer` | **M6** | Medium | Underperforming agents degrade tier; closes the autonomy loop |
| Multi-tenant Postgres-backed ledgers | **M6** | Medium | Persistent cost/value storage with `tenant_id` partitioning |
| Exporters to Langfuse / Fiddler / Arize | **M6** | Medium | Cost + value events flow to external dashboards |

**MVP (M4 slice, ~5 days):** Trace IDs in audit events + cost ledger emission from GovernedModelProvider. Already differentiated, already useful, sets up Stages 3–5.

---

## Prior Art & Research

### Industry Frameworks Referenced

| Source | Key contribution | How it informs this RFC |
|---|---|---|
| **Alatirok CFO-Ready Framework** (2026) | Two-ledger model (cost + value); what survives CFO review | `CostLedger` / `ValueLedger` separation; `ValueBaseline` as CFO artifact |
| **Salesforce Agentforce AWU** | "Agentic Work Units" — measures discrete tasks, not tokens | Outcome-based measurement, not token-based |
| **Explore Agentic AI Playbook** | Baseline-first methodology using Forrester TEI | `ValueBaseline` required before deployment |
| **Fiddler AI** | Four-category benefits: cost, revenue, risk, optionality | Extensible `values` dict on Event supports all four |
| **FinOps Foundation** | Inform → Optimize → Operate; agent cost multiplier (5–50× per interaction) | Budget guardrails at feature level, not team level |
| **Digital Applied** | Four token layers × three attribution dimensions | Tag conventions on `scoring.Event` |
| **Langfuse case study** | Per-tenant cost attribution; 40× outlier identified day 3 | Emit events, let Langfuse dashboard |
| **KPMG AI ROI** | Six practical principles; stress-test realization assumptions | Baseline methodology in `ValueBaseline` |
| **IBM** | Three ROI lenses: speed-to-outcome, cost-to-serve, new capabilities | `OutcomeBinding` supports all three via flexible `success_criteria` |

### Academic Research Referenced

| Source | Key contribution | How it informs this RFC |
|---|---|---|
| **Agentproof** (2026) | Cross-framework workflow graph extraction | Compatible — receives trace IDs, doesn't extract graphs |
| **GraSP** (2026) | Executable skill graphs as typed DAGs | Confirms DAG as topology model; forest = parallel independent trees |
| **SHARP** (2026) | Shapley-based hierarchical credit assignment | Future work — emit data, let attribution engines run |
| **Agent That Matters** (ICLR 2026) | Leave-One-Out as reliable, efficient Shapley proxy | LOO 3–7× cheaper; viable for M6+ attribution layer |
| **AdaptOrch** (2026) | Four canonical topologies; topology selection outweighs model selection by 12–23% | Topology awareness as value multiplier |
| **NIST AI RMF** | MAP 3.1/3.2: document expected benefits and costs before deployment | Registration-time enforcement of baseline declaration |

---

## Open Questions

1. **Granularity of cost attribution**: Should Presidium track four token layers (prompt/tool/memory/response) or leave that to the provider gateway? Lean toward emitting a single `cost_usd` per call, with token breakdown as optional metadata.

2. **Baseline enforcement in dev environments**: `require-outcome-binding` policy blocks agent registration without a baseline. In dev, this is friction. Propose: `--placeholder` mode that auto-generates a stub baseline, with a registration policy that distinguishes `dev` from `prod` enforcement mode.

3. **Multi-agent value attribution**: When 5 agents collaborate on one outcome, which agent gets the value? V1: attribute full value to the workflow root agent. Future: LOO-based fractional attribution.

4. **Value capture trigger**: Should value events be emitted automatically when `success_criteria` evaluates true in POST_TOOL, or should the caller explicitly emit them? Lean toward automatic — it's the whole point of governance.

5. **Integration with RFC-002 (Multi-Dimensional Evaluation)**: When multi-dimensional trust arrives (M4), ROI should be a first-class dimension alongside behavioral trust. The `MultiDimensionalTrustScorer` Protocol already supports string-keyed dimensions — `"roi"` slots in naturally.

---

## Decision

Accept this RFC as the design direction for agent value chain in Presidium. Implementation begins in M4 with trace context and cost ledger foundation.

The core principle — **value as policy, not dashboard** — differentiates Presidium from every observability vendor and positions governance as the layer that makes AI investment defensible.
