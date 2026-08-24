"""Real tests for ListApprovalsGatewayAgent/ApproveGatewayAgent/DenyGatewayAgent -- direct
handle_call() invocation, matching test_registry_agent.py's own established pattern.

Uses the real presidium.approval.CallbackApprovalProvider (manual mode -- no callback/
auto_approve/auto_deny), not a fake, so request_approval()'s real Future-based pending/decide
mechanism is genuinely exercised.
"""

from __future__ import annotations

import asyncio

from presidium.approval import CallbackApprovalProvider
from presidium.model import ApprovalDecision, ApprovalRequest
from presidium_contrib.server import (
    ApproveGatewayAgent,
    DenyGatewayAgent,
    ListApprovalsGatewayAgent,
)


def _make_request(request_id: str = "req-1") -> ApprovalRequest:
    return ApprovalRequest(
        request_id=request_id,
        agent_id="presidium://acme.com/researcher",
        resource="tool:database",
        action="write",
        reason="Low trust write",
        approvers=["security@acme.com"],
        context={},
        policy_name="trust-gate",
        timeout_seconds=5.0,
    )


class TestListApprovalsGatewayAgent:
    async def test_list_empty(self) -> None:
        service = CallbackApprovalProvider()
        agent = ListApprovalsGatewayAgent(approval_service=service)

        result = await agent.handle_call({}, "sender")

        assert result == {"status": "ok", "approvals": []}

    async def test_list_returns_a_real_pending_request(self) -> None:
        service = CallbackApprovalProvider()
        # request_approval() blocks until decide()/timeout -- run it as a background task so
        # this test can observe it as genuinely pending, matching how GovernedToolProvider.
        # check() actually calls it (awaited from a different coroutine than the one listing).
        task = asyncio.ensure_future(service.request_approval(_make_request()))
        await asyncio.sleep(0.01)  # let request_approval() register itself as pending

        agent = ListApprovalsGatewayAgent(approval_service=service)
        result = await agent.handle_call({}, "sender")

        assert result["status"] == "ok"
        assert len(result["approvals"]) == 1
        assert result["approvals"][0]["request_id"] == "req-1"
        assert result["approvals"][0]["status"] == "pending"
        assert result["approvals"][0]["approvers"] == ["security@acme.com"]

        # Real cleanup -- resolve the still-pending request so the test doesn't leak a task.
        await service.decide(
            "req-1", ApprovalDecision(request_id="req-1", approved=True, decided_by="test")
        )
        await task


class TestApproveGatewayAgent:
    async def test_approve_resolves_a_real_pending_request(self) -> None:
        service = CallbackApprovalProvider()
        task = asyncio.ensure_future(service.request_approval(_make_request()))
        await asyncio.sleep(0.01)

        agent = ApproveGatewayAgent(approval_service=service)
        result = await agent.handle_call({"id": "req-1"}, "sender")

        assert result == {"status": "decided", "decision": "approved", "request_id": "req-1"}

        decision = await task
        assert decision.approved is True

    async def test_approve_missing_id_path_param(self) -> None:
        service = CallbackApprovalProvider()
        agent = ApproveGatewayAgent(approval_service=service)

        result = await agent.handle_call({}, "sender")

        assert result["status"] == "error"

    async def test_approve_unknown_request_id_is_a_real_honest_noop(self) -> None:
        """Real, honest limit: ApprovalService.decide() has no way to report "no such pending
        request" -- confirmed this genuinely returns a "decided" reply even for an id that was
        never pending, matching the underlying Protocol's own real, silent-no-op contract."""
        service = CallbackApprovalProvider()
        agent = ApproveGatewayAgent(approval_service=service)

        result = await agent.handle_call({"id": "ghost"}, "sender")

        assert result == {"status": "decided", "decision": "approved", "request_id": "ghost"}

    async def test_approve_with_custom_decided_by_and_reason(self) -> None:
        service = CallbackApprovalProvider()
        task = asyncio.ensure_future(service.request_approval(_make_request()))
        await asyncio.sleep(0.01)

        agent = ApproveGatewayAgent(approval_service=service)
        await agent.handle_call(
            {"id": "req-1", "decided_by": "alice@acme.com", "reason": "Looks fine"}, "sender"
        )

        decision = await task
        assert decision.decided_by == "alice@acme.com"
        assert decision.reason == "Looks fine"


class TestDenyGatewayAgent:
    async def test_deny_resolves_a_real_pending_request(self) -> None:
        service = CallbackApprovalProvider()
        task = asyncio.ensure_future(service.request_approval(_make_request()))
        await asyncio.sleep(0.01)

        agent = DenyGatewayAgent(approval_service=service)
        result = await agent.handle_call({"id": "req-1"}, "sender")

        assert result == {"status": "decided", "decision": "denied", "request_id": "req-1"}

        decision = await task
        assert decision.approved is False

    async def test_deny_missing_id_path_param(self) -> None:
        service = CallbackApprovalProvider()
        agent = DenyGatewayAgent(approval_service=service)

        result = await agent.handle_call({}, "sender")

        assert result["status"] == "error"
