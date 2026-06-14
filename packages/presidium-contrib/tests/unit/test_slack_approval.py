from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from presidium.model import ApprovalDecision, ApprovalRequest, ApprovalStatus
from presidium_contrib.slack.approval import SlackApprovalService


def _make_request(request_id: str = "req-001", timeout: float = 5.0) -> ApprovalRequest:
    return ApprovalRequest(
        request_id=request_id,
        agent_id="presidium://local/test",
        resource="tool:database",
        action="write",
        reason="Low trust",
        approvers=["admin@acme.com"],
        context={},
        policy_name="trust-gate",
        timeout_seconds=timeout,
    )


class TestSlackApprovalService:
    async def test_posts_to_slack_and_waits_for_decide(self) -> None:
        with patch("presidium_contrib.slack.approval.AsyncWebClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value = mock_client

            service = SlackApprovalService(token="xoxb-test", channel="#approvals")
            req = _make_request()

            async def approve_later() -> None:
                await asyncio.sleep(0.05)
                await service.decide(
                    "req-001",
                    ApprovalDecision(request_id="req-001", approved=True, decided_by="human"),
                )

            task = asyncio.create_task(approve_later())
            decision = await service.request_approval(req)
            await task

            assert decision.approved is True
            assert req.status == ApprovalStatus.APPROVED
            mock_client.chat_postMessage.assert_called_once()
            call_kwargs = mock_client.chat_postMessage.call_args[1]
            assert call_kwargs["channel"] == "#approvals"
            assert "blocks" in call_kwargs

    async def test_timeout_auto_denies(self) -> None:
        with patch("presidium_contrib.slack.approval.AsyncWebClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value = mock_client

            service = SlackApprovalService(token="xoxb-test", channel="#approvals")
            req = _make_request(timeout=0.05)
            decision = await service.request_approval(req)

            assert decision.approved is False
            assert decision.reason == "timed out"
            assert req.status == ApprovalStatus.TIMED_OUT

    async def test_slack_delivery_failure_denies(self) -> None:
        with patch("presidium_contrib.slack.approval.AsyncWebClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.chat_postMessage.side_effect = Exception("slack api error")
            mock_client_cls.return_value = mock_client

            service = SlackApprovalService(token="xoxb-test", channel="#approvals")
            req = _make_request()
            decision = await service.request_approval(req)

            assert decision.approved is False
            assert decision.reason == "Slack delivery failed"
            assert req.status == ApprovalStatus.DENIED

    async def test_blocks_contain_approve_deny_buttons(self) -> None:
        with patch("presidium_contrib.slack.approval.AsyncWebClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value = mock_client

            service = SlackApprovalService(token="xoxb-test", channel="#approvals")
            req = _make_request(timeout=0.05)
            await service.request_approval(req)

            call_kwargs = mock_client.chat_postMessage.call_args[1]
            blocks = call_kwargs["blocks"]
            actions_block = [b for b in blocks if b["type"] == "actions"][0]
            action_ids = [e["action_id"] for e in actions_block["elements"]]
            assert "presidium_approve" in action_ids
            assert "presidium_deny" in action_ids

    async def test_pending_list(self) -> None:
        with patch("presidium_contrib.slack.approval.AsyncWebClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client_cls.return_value = mock_client

            service = SlackApprovalService(token="xoxb-test", channel="#approvals")
            req = _make_request(timeout=5.0)

            async def check_and_decide() -> list[ApprovalRequest]:
                await asyncio.sleep(0.05)
                pending = await service.list_pending()
                await service.decide(
                    "req-001",
                    ApprovalDecision(request_id="req-001", approved=True, decided_by="admin"),
                )
                return pending

            task = asyncio.create_task(check_and_decide())
            await service.request_approval(req)
            pending = await task
            assert len(pending) == 1

    async def test_decide_nonexistent_is_noop(self) -> None:
        with patch("presidium_contrib.slack.approval.AsyncWebClient") as mock_client_cls:
            mock_client_cls.return_value = AsyncMock()
            service = SlackApprovalService(token="xoxb-test", channel="#approvals")
            await service.decide(
                "nonexistent",
                ApprovalDecision(request_id="nonexistent", approved=True, decided_by="admin"),
            )
