# Design: Approval Service

> Human-in-the-loop enforcement for REQUIRE_APPROVAL policy decisions.

**Status:** Draft (June 2026)
**Package:** `presidium` (protocol + CallbackApprovalProvider) / `presidium-contrib` (Slack, Temporal, webhook adapters)
**Milestone:** M2
**Requirements:** [approval-service-requirements.md](approval-service-requirements.md)

## Problem Statement

When a policy evaluates to REQUIRE_APPROVAL, something needs to happen: the action must be paused, a human must be notified, and the system must wait for a decision. Without a formalized service, each team builds ad-hoc approval flows with no audit trail, no timeout handling, and no integration with the governance stack.

EU AI Act Article 14 requires human oversight mechanisms. Singapore's agentic AI framework requires escalation paths. The ApprovalService is the runtime mechanism that satisfies these regulatory requirements.

## Goals

1. Formalize the HITL pattern as a Protocol with pluggable backends
2. Async, non-blocking approval waiting — agents keep processing other work
3. Fail-closed on timeout — unanswered requests auto-deny
4. Audit trail for every request and decision
5. Approval records feed M4 decision journal for autonomy progression

## Non-Goals (M2)

- Multi-approver consensus — M3
- Approval delegation chains — M3
- Approval SLAs with escalation — M3
- Dashboard / UI for approval management — M5

---

## Architecture

```
PolicyEngine returns REQUIRE_APPROVAL
    ↓
GovernedToolProvider (PEP)
    ↓ creates ApprovalRequest
    ↓ calls ApprovalService.request_approval()
    ↓ awaits decision (async, with timeout)
ApprovalService
    ↓ persists request
    ↓ routes to approvers via backend
    ↓ waits for decision or timeout
    ↓ returns ApprovalDecision
GovernedToolProvider
    ↓ APPROVED → delegate to underlying ToolProvider
    ↓ DENIED / TIMEOUT → raise PolicyDeniedError
```

---

## Data Model

### ApprovalRequest

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"

@dataclass
class ApprovalRequest:
    """A request for human approval of an agent action."""
    request_id: str                       # Unique ID (UUID)
    agent_id: str                         # presidium:// URI of requesting agent
    resource: str                         # What the agent wants to access (e.g., "tool:database")
    action: str                           # What the agent wants to do (e.g., "write")
    reason: str                           # Why approval is needed (from PolicyResult.reason)
    approvers: list[str]                  # Who can approve (from PolicyRule.approvers)
    context: dict[str, Any]               # Additional context for the approver
    policy_name: str                      # Which policy triggered REQUIRE_APPROVAL
    
    status: ApprovalStatus = ApprovalStatus.PENDING
    decision_by: str | None = None        # Approver identity
    decision_reason: str | None = None    # Approver's explanation
    
    created_at: datetime = field(default_factory=lambda: datetime.now())
    decided_at: datetime | None = None
    timeout_seconds: float = 300.0        # Default 5 minutes

@dataclass
class ApprovalDecision:
    """The result of an approval request."""
    request_id: str
    approved: bool
    decided_by: str                       # Approver identity
    reason: str | None = None
    decided_at: datetime = field(default_factory=lambda: datetime.now())
```

### Context Provided to Approvers

The `context` dict gives approvers the information they need to make a decision:

```python
context = {
    "agent_name": "researcher",
    "agent_id": "presidium://acme.com/prod/researcher",
    "trust_tier": "standard",
    "trust_value": 0.6,
    "grant_matched": "tool:database:write (conditional: trust >= 0.7)",
    "action_details": {
        "tool": "database",
        "operation": "write",
        "parameters": {"table": "reports", "data_size": "1.2MB"},
    },
    "recent_violations": 0,
    "last_approval": "2026-06-10T14:30:00Z (approved by alice@acme.com)",
}
```

---

## ApprovalService Protocol

```python
class ApprovalService(Protocol):
    """Protocol for human-in-the-loop approval."""
    
    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        """Submit an approval request and await the decision.
        
        Blocks (async) until an approver responds or the timeout expires.
        On timeout, returns an auto-denied decision.
        Emits audit events for request creation and decision.
        """
        ...
    
    async def list_pending(self) -> list[ApprovalRequest]:
        """Return all pending approval requests."""
        ...
    
    async def decide(self, request_id: str, decision: ApprovalDecision) -> None:
        """Submit a decision for a pending request (called by approver backend)."""
        ...
```

---

## Default Implementation: CallbackApprovalProvider

```python
class CallbackApprovalProvider:
    """Default ApprovalService for dev and test.
    
    Approval decisions are submitted via a programmatic callback.
    No external infrastructure required.
    
    Usage in tests:
        provider = CallbackApprovalProvider()
        
        # Auto-approve everything (for happy-path tests)
        provider.auto_approve = True
        
        # Or use manual callback
        async def my_approver(request):
            return ApprovalDecision(
                request_id=request.request_id,
                approved=True,
                decided_by="test-harness",
            )
        provider.callback = my_approver
    """
    
    def __init__(self):
        self.auto_approve: bool = False
        self.auto_deny: bool = False
        self.callback: Callable | None = None
        self._pending: dict[str, ApprovalRequest] = {}
        self._decisions: dict[str, asyncio.Future] = {}
    
    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        if self.auto_approve:
            return ApprovalDecision(
                request_id=request.request_id,
                approved=True,
                decided_by="auto-approve",
            )
        if self.auto_deny:
            return ApprovalDecision(
                request_id=request.request_id,
                approved=False,
                decided_by="auto-deny",
            )
        if self.callback:
            return await self.callback(request)
        
        # Manual mode: store pending, wait for decide() call
        self._pending[request.request_id] = request
        future = asyncio.get_event_loop().create_future()
        self._decisions[request.request_id] = future
        
        try:
            return await asyncio.wait_for(future, timeout=request.timeout_seconds)
        except asyncio.TimeoutError:
            return ApprovalDecision(
                request_id=request.request_id,
                approved=False,
                decided_by="timeout",
                reason="Approval request timed out",
            )
    
    async def decide(self, request_id: str, decision: ApprovalDecision) -> None:
        future = self._decisions.get(request_id)
        if future and not future.done():
            future.set_result(decision)
```

---

## Contrib Implementations (M3)

### SlackApprovalProvider (`presidium-contrib[slack]`)

```python
class SlackApprovalProvider:
    """Routes approval requests to a Slack channel with approve/deny buttons.
    
    Config:
        slack_token: Bot token with chat:write + interactive permission
        channel_id: Channel to post approval requests
        
    Flow:
        1. Post message to channel with agent name, action, reason, context
        2. Message includes "Approve" and "Deny" buttons (Slack Block Kit)
        3. User clicks button → Slack webhook → decide() called
        4. Original message updated with decision status
    """
```

### TemporalApprovalProvider (`presidium-contrib[temporal]`)

```python
class TemporalApprovalProvider:
    """Creates a Temporal human task workflow for approval.
    
    Flow:
        1. Start a Temporal workflow with the approval request
        2. Workflow creates a human task (Signal-based)
        3. Approver completes the task via Temporal UI or API
        4. Signal received → decide() called
        5. Workflow completes with decision
    """
```

### WebhookApprovalProvider (`presidium-contrib[webhook]`)

```python
class WebhookApprovalProvider:
    """POSTs approval requests to a webhook URL and listens for callbacks.
    
    Config:
        webhook_url: URL to POST approval requests to
        callback_path: HTTP path to listen for approval decisions
        
    Flow:
        1. POST request details to webhook_url
        2. External system processes the request
        3. External system POSTs decision to callback_path
        4. decide() called with the decision
    """
```

---

## PEP Integration

How the GovernedToolProvider uses the ApprovalService:

```python
class GovernedToolProvider:
    async def execute(self, tool_name: str, agent_name: str, **kwargs):
        # ... policy evaluation ...
        
        if result.decision == PolicyDecision.REQUIRE_APPROVAL:
            request = ApprovalRequest(
                request_id=str(uuid.uuid4()),
                agent_id=agent_record.agent_id,
                resource=f"tool:{tool_name}",
                action="invoke",
                reason=result.reason,
                approvers=result.approvers,
                context={
                    "agent_name": agent_name,
                    "trust_tier": str(agent_record.trust_tier),
                    "trust_value": agent_record.trust_value,
                    "parameters": kwargs,
                },
                policy_name=result.policy_name,
                timeout_seconds=policy_timeout,
            )
            
            decision = await self._approval_service.request_approval(request)
            
            if not decision.approved:
                await self._audit_denied(request, decision)
                raise PolicyDeniedError(
                    f"Approval denied by {decision.decided_by}: {decision.reason}"
                )
            
            await self._audit_approved(request, decision)
        
        # Proceed with tool call
        return await self._provider.execute(tool_name, **kwargs)
```

---

## Audit Events

```python
# Request created
AuditEvent(
    event="approval.requested",
    ts="2026-06-11T10:00:00Z",
    agent="presidium://acme.com/prod/researcher",
    signer_id="presidium://acme.com/prod/researcher",
    details={
        "request_id": "req-uuid-123",
        "resource": "tool:database",
        "action": "write",
        "policy_name": "trust-gate-writes",
        "approvers": ["security-team@acme.com"],
        "timeout_seconds": 300,
    }
)

# Decision received
AuditEvent(
    event="approval.decided",
    ts="2026-06-11T10:15:00Z",
    agent="presidium://acme.com/prod/researcher",
    signer_id="alice@acme.com",
    details={
        "request_id": "req-uuid-123",
        "decision": "approved",
        "decided_by": "alice@acme.com",
        "reason": "Routine report generation, approved",
        "wait_time_seconds": 900,
    }
)
```

---

## Topology YAML

```yaml
presidium:
  approval:
    backend: callback           # "callback" | "slack" | "temporal" | "webhook"
    default_timeout: 300        # seconds (5 minutes)
    
    # Slack config (presidium-contrib[slack])
    # slack_token: ${SLACK_BOT_TOKEN}
    # slack_channel: C01234567
    
    # Webhook config (presidium-contrib[webhook])
    # webhook_url: https://approvals.internal/api/v1/requests
    # callback_path: /presidium/approval-callback
```

---

## Connection to Autonomy Progression (M4)

Approval records are **training data for the decision journal**. The M4 autonomy progression uses approval history to learn:
- Which actions get approved vs denied
- How quickly approvals happen (fast approval = routine action, candidate for auto-approval)
- Which agents get more approvals over time (trust building signal)
- Which approvers approve what (approver behavior patterns)

The approval record schema (FR-5.2) is designed with this downstream use in mind — every field needed for the decision journal is already captured.

---

## Design Decisions

| # | Decision | Choice | Alternatives Considered | Rationale |
|---|---|---|---|---|
| A1 | Async waiting | PEP awaits with timeout; agent message loop continues | Block entire agent, fire-and-forget | Blocking wastes agent capacity. Fire-and-forget loses the enforcement point. Async await is the Civitas pattern. |
| A2 | Fail-closed on timeout | Auto-deny after configurable timeout (default 5 min) | Auto-approve, keep pending forever | Security invariant. Unanswered requests must not pass. Same principle as PolicyEngine fail-closed. |
| A3 | Default backend | CallbackApprovalProvider | Stdin prompt, Slack-only | Callback enables programmatic testing. Stdin doesn't work in headless environments. Slack requires infrastructure. |
| A4 | Approval records | Persisted, queryable, designed for M4 decision journal | In-memory only, no persistence | Approval history is the training data for autonomy progression. Losing it loses the learning opportunity. |
| A5 | Context richness | Full agent context sent to approvers | Minimal (just agent name + action) | Approvers need context to make good decisions. Trust tier, recent violations, last approval — all relevant. |

---

## Open Questions (Deferred)

1. **Multi-approver consensus**: should some actions require N of M approvers? (M3)
2. **Approval delegation**: can an approver delegate to someone else? (M3)
3. **Approval SLAs**: should the system escalate to a backup approver after X minutes? (M3)
4. **Batch approval**: can an approver approve a class of actions ("approve all database reads for this agent for the next hour")? (M3)
5. **Approval revocation**: can an approver revoke a previously given approval? (M3)
