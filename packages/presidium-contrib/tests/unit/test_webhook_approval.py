from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from presidium.model import ApprovalDecision, ApprovalRequest, ApprovalStatus
from presidium_contrib.webhook.approval import WebhookApprovalProvider


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


class TestWebhookApprovalProvider:
    async def test_posts_to_webhook_and_waits_for_decide(self) -> None:
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None

        with patch("presidium_contrib.webhook.approval.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            provider = WebhookApprovalProvider("https://hooks.example.com/approve")
            req = _make_request()

            async def approve_later() -> None:
                await asyncio.sleep(0.05)
                await provider.decide(
                    "req-001",
                    ApprovalDecision(
                        request_id="req-001",
                        approved=True,
                        decided_by="human",
                    ),
                )

            task = asyncio.create_task(approve_later())
            decision = await provider.request_approval(req)
            await task

            assert decision.approved is True
            assert req.status == ApprovalStatus.APPROVED
            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "https://hooks.example.com/approve"
            assert call_args[1]["json"]["request_id"] == "req-001"

    async def test_timeout_auto_denies(self) -> None:
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None

        with patch("presidium_contrib.webhook.approval.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            provider = WebhookApprovalProvider("https://hooks.example.com/approve")
            req = _make_request(timeout=0.05)
            decision = await provider.request_approval(req)

            assert decision.approved is False
            assert decision.reason == "timed out"
            assert req.status == ApprovalStatus.TIMED_OUT

    async def test_webhook_delivery_failure_denies(self) -> None:
        with patch("presidium_contrib.webhook.approval.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("connection refused")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            provider = WebhookApprovalProvider("https://hooks.example.com/approve")
            req = _make_request()
            decision = await provider.request_approval(req)

            assert decision.approved is False
            assert decision.reason == "webhook delivery failed"
            assert req.status == ApprovalStatus.DENIED

    async def test_pending_list(self) -> None:
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None

        with patch("presidium_contrib.webhook.approval.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            provider = WebhookApprovalProvider("https://hooks.example.com/approve")
            req = _make_request(timeout=5.0)

            async def check_and_decide() -> list[ApprovalRequest]:
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

            task = asyncio.create_task(check_and_decide())
            await provider.request_approval(req)
            pending = await task
            assert len(pending) == 1
            assert pending[0].request_id == "req-001"

    async def test_custom_headers_sent(self) -> None:
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None

        with patch("presidium_contrib.webhook.approval.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post.return_value = mock_response
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            provider = WebhookApprovalProvider(
                "https://hooks.example.com/approve",
                headers={"Authorization": "Bearer tok-123"},
            )
            req = _make_request(timeout=0.05)
            await provider.request_approval(req)

            call_kwargs = mock_client.post.call_args[1]
            assert call_kwargs["headers"]["Authorization"] == "Bearer tok-123"
