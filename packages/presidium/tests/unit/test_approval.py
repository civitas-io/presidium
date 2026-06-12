from __future__ import annotations

import asyncio

from presidium.approval import ApprovalService, CallbackApprovalProvider
from presidium.model import ApprovalDecision, ApprovalRequest, ApprovalStatus


def _make_request(
    request_id: str = "req-001",
    timeout: float = 300.0,
) -> ApprovalRequest:
    return ApprovalRequest(
        request_id=request_id,
        agent_id="presidium://local/test",
        resource="tool:database",
        action="write",
        reason="Low trust for write",
        approvers=["security@acme.com"],
        context={"trust_value": 0.5},
        policy_name="trust-gate-writes",
        timeout_seconds=timeout,
    )


class TestCallbackApprovalProviderProtocol:
    def test_satisfies_protocol(self) -> None:
        provider = CallbackApprovalProvider()
        assert isinstance(provider, ApprovalService)


class TestAutoApprove:
    async def test_auto_approve(self) -> None:
        provider = CallbackApprovalProvider(auto_approve=True)
        req = _make_request()
        decision = await provider.request_approval(req)
        assert decision.approved is True
        assert decision.reason == "auto-approved"
        assert req.status == ApprovalStatus.APPROVED


class TestAutoDeny:
    async def test_auto_deny(self) -> None:
        provider = CallbackApprovalProvider(auto_deny=True)
        req = _make_request()
        decision = await provider.request_approval(req)
        assert decision.approved is False
        assert decision.reason == "auto-denied"
        assert req.status == ApprovalStatus.DENIED


class TestCallbackMode:
    async def test_callback_approved(self) -> None:
        async def approve_callback(req: ApprovalRequest) -> ApprovalDecision:
            return ApprovalDecision(
                request_id=req.request_id,
                approved=True,
                decided_by="admin",
                reason="looks good",
            )

        provider = CallbackApprovalProvider(callback=approve_callback)
        req = _make_request()
        decision = await provider.request_approval(req)
        assert decision.approved is True
        assert decision.decided_by == "admin"
        assert req.status == ApprovalStatus.APPROVED

    async def test_callback_denied(self) -> None:
        async def deny_callback(req: ApprovalRequest) -> ApprovalDecision:
            return ApprovalDecision(
                request_id=req.request_id,
                approved=False,
                decided_by="admin",
            )

        provider = CallbackApprovalProvider(callback=deny_callback)
        req = _make_request()
        decision = await provider.request_approval(req)
        assert decision.approved is False
        assert req.status == ApprovalStatus.DENIED


class TestManualMode:
    async def test_decide_resolves_future(self) -> None:
        provider = CallbackApprovalProvider()
        req = _make_request(timeout=5.0)

        async def approve_later() -> None:
            await asyncio.sleep(0.05)
            await provider.decide(
                "req-001",
                ApprovalDecision(
                    request_id="req-001",
                    approved=True,
                    decided_by="human",
                    reason="confirmed",
                ),
            )

        task = asyncio.create_task(approve_later())
        decision = await provider.request_approval(req)
        await task
        assert decision.approved is True
        assert decision.decided_by == "human"
        assert req.status == ApprovalStatus.APPROVED

    async def test_timeout_auto_denies(self) -> None:
        provider = CallbackApprovalProvider()
        req = _make_request(timeout=0.05)
        decision = await provider.request_approval(req)
        assert decision.approved is False
        assert decision.reason == "timed out"
        assert req.status == ApprovalStatus.TIMED_OUT

    async def test_pending_list(self) -> None:
        provider = CallbackApprovalProvider()
        req = _make_request(timeout=5.0)

        async def check_pending() -> list[ApprovalRequest]:
            await asyncio.sleep(0.05)
            pending = await provider.list_pending()
            await provider.decide(
                "req-001",
                ApprovalDecision(
                    request_id="req-001",
                    approved=True,
                    decided_by="admin",
                ),
            )
            return pending

        task = asyncio.create_task(check_pending())
        await provider.request_approval(req)
        pending = await task
        assert len(pending) == 1
        assert pending[0].request_id == "req-001"

    async def test_pending_cleared_after_decision(self) -> None:
        provider = CallbackApprovalProvider()
        req = _make_request(timeout=0.05)
        await provider.request_approval(req)
        pending = await provider.list_pending()
        assert len(pending) == 0

    async def test_decide_nonexistent_is_noop(self) -> None:
        provider = CallbackApprovalProvider()
        await provider.decide(
            "nonexistent",
            ApprovalDecision(
                request_id="nonexistent",
                approved=True,
                decided_by="admin",
            ),
        )
