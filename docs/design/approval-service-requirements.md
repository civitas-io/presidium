# Approval Service: Requirements

> What the ApprovalService must do — the HITL enforcement point for REQUIRE_APPROVAL policy decisions.
> Status: Draft
> Milestone: M2 (Core Interfaces + CEL Policy)

## Overview

When the PolicyEngine returns `REQUIRE_APPROVAL`, the enforcement point (GovernedModelProvider or GovernedToolProvider) needs to route the request to a human for approval. The ApprovalService manages this interaction: creating approval requests, routing them to the right approvers, waiting for a decision, and returning the result to the blocked agent.

This is the bridge between autonomous agent operation and human oversight. EU AI Act Article 14 requires human oversight mechanisms for high-risk AI. Singapore's 2026 agentic AI framework requires escalation paths for out-of-scope actions. The ApprovalService provides the runtime mechanism that satisfies these requirements.

Civitas already demonstrates the HITL pattern in `examples/patterns/human_in_the_loop.py`: agents store pending state in `self.state`, reply with a "needs_approval" signal, and resume when an approval message arrives. The ApprovalService formalizes this pattern as a Protocol with pluggable backends (callback, Slack, Temporal, HTTP webhook).

---

## Functional Requirements

### FR-1: Approval Request Creation

**FR-1.1**: The ApprovalService MUST accept an approval request containing: agent_id (who is requesting), action (what they want to do — resource + action), reason (why approval is needed — from PolicyResult), approvers (who can approve — from PolicyRule), context (additional data for the approver — agent trust tier, grant details).
**FR-1.2**: Each approval request MUST be assigned a unique request_id.
**FR-1.3**: The approval request MUST be persisted so it survives agent restarts (using Civitas StateStore or equivalent).
**FR-1.4**: Creating an approval request MUST emit an audit event.

### FR-2: Approval Decision

**FR-2.1**: An approver MUST be able to approve or deny a pending request.
**FR-2.2**: An approval decision MUST include: decision (approve/deny), approver identity (who decided), reason (optional — why they approved or denied), timestamp.
**FR-2.3**: The decision MUST be persisted as part of the approval record.
**FR-2.4**: The decision MUST emit an audit event.
**FR-2.5**: A denied request MUST NOT allow the agent to proceed with the action.

### FR-3: Waiting and Timeout

**FR-3.1**: The PEP (GovernedModelProvider/GovernedToolProvider) MUST await the approval decision asynchronously — the agent's message loop continues processing other messages while waiting.
**FR-3.2**: Approval requests MUST have a configurable timeout (default: 5 minutes). After timeout, the request is auto-denied.
**FR-3.3**: Timeout MUST be configurable per-policy rule (via the PolicyRule's configuration).
**FR-3.4**: On timeout, an audit event MUST be emitted with reason "approval_timeout".

**Scenario**: Agent "writer" attempts a production database write. The PolicyEngine returns REQUIRE_APPROVAL with approvers: ["security-team@acme.com"]. The GovernedToolProvider creates an approval request via the ApprovalService. The agent's tool call is suspended, but the agent continues processing other messages. 15 minutes later, a security team member approves the request. The tool call proceeds.

**Scenario**: Same as above, but no one responds within 5 minutes. The request is auto-denied. The agent receives a PolicyDeniedError with reason "approval_timeout". The agent can retry, which creates a new approval request.

### FR-4: Approval Routing

**FR-4.1**: The ApprovalService MUST support routing approval requests to approvers via the configured backend.
**FR-4.2**: For the `CallbackApprovalProvider` (default), approval requests MUST be resolvable via a programmatic callback (for testing and dev).
**FR-4.3**: For contrib backends (Slack, Temporal, webhook), routing is backend-specific: Slack sends a message with approve/deny buttons, Temporal creates a human task, webhook POSTs to a URL.
**FR-4.4**: If no approver responds and timeout is reached, the request is auto-denied (fail-closed).

### FR-5: Approval Record

**FR-5.1**: The ApprovalService MUST maintain a queryable record of all approval requests and their outcomes.
**FR-5.2**: Each record MUST include: request_id, agent_id, action (resource + action), reason, approvers, status (pending/approved/denied/timed_out), decision_by (approver identity if decided), decision_reason, created_at, decided_at.
**FR-5.3**: Approval records MUST be accessible for audit and for the autonomy progression (M4 decision journal uses approval history to learn trust patterns).

### FR-6: Protocol and Extensibility

**FR-6.1**: `ApprovalService` MUST be a Protocol — backends are swappable.
**FR-6.2**: `CallbackApprovalProvider` MUST be the default implementation in the `presidium` core package (programmatic callbacks for dev/test).
**FR-6.3**: Contrib backends: `SlackApprovalProvider` (`presidium-contrib[slack]`), `TemporalApprovalProvider` (`presidium-contrib[temporal]`), `WebhookApprovalProvider` (`presidium-contrib[webhook]`).

### FR-7: Integration with Policy Engine

**FR-7.1**: The ApprovalService MUST receive the `PolicyResult` from the PEP when the decision is `REQUIRE_APPROVAL`.
**FR-7.2**: The `PolicyResult.approvers` list MUST be passed through to the ApprovalService for routing.
**FR-7.3**: The PEP MUST await the approval decision before proceeding (async await with timeout).

---

## Non-Functional Requirements

### NFR-1: Availability
- Approval request creation MUST NOT block the agent's message loop (async, non-blocking)
- Agent MUST continue processing other messages while waiting for approval
- Approval requests MUST survive agent restarts (persisted)

### NFR-2: Security
- Only listed approvers MUST be able to approve or deny a request
- Approval decisions MUST be tamper-evident (audit trail)

### NFR-3: CNCF Alignment
- Audit events via OpenTelemetry (via Civitas AuditSink)

---

## Design Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| A1 | Async waiting | PEP awaits with timeout; agent message loop continues | Blocking the agent entirely would prevent it from handling other work. Async matches Civitas's asyncio model. |
| A2 | Fail-closed on timeout | Auto-deny after configurable timeout (default 5 min) | Unanswered approval requests must not leave agents hanging indefinitely. Fail-closed is the security default. |
| A3 | Default backend | CallbackApprovalProvider (programmatic) | Dev and test need approval without Slack/Temporal infrastructure. Callback allows automated testing of approval flows. |
| A4 | Approval record persistence | Records stored for audit and M4 decision journal | Approval history is training data for the autonomy progression — which actions get approved, by whom, how quickly. |
| A5 | Approver identity | From PolicyRule.approvers list | Policy defines who can approve. The ApprovalService routes to them. Separation of concerns. |

---

## Out of Scope (M2)

- Multi-approver consensus (require N of M approvers) — M3
- Approval delegation (approver delegates to another person) — M3
- Approval workflows (sequential approval chains) — M3
- Approval SLAs (escalate to backup approver after X minutes) — M3
- Approval analytics dashboard — M5
- Integration with the decision journal (M4 — approval records become training data for learned autonomy)
