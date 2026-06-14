"""WebhookApprovalProvider — POST approval requests to a webhook URL."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from presidium.model import ApprovalDecision, ApprovalRequest, ApprovalStatus

logger = logging.getLogger(__name__)


class WebhookApprovalProvider:
    """Posts approval requests to a webhook URL and waits for a callback.

    On REQUIRE_APPROVAL, POSTs the request as JSON to ``webhook_url``.
    Then waits up to ``timeout_seconds`` for a call to ``decide()``
    (typically from an HTTP callback handler). Fail-closed on timeout.
    """

    def __init__(
        self,
        webhook_url: str,
        *,
        timeout_seconds: float = 300.0,
        decided_by: str = "webhook",
        headers: dict[str, str] | None = None,
    ) -> None:
        self._webhook_url = webhook_url
        self._timeout = timeout_seconds
        self._decided_by = decided_by
        self._headers = headers or {}
        self._pending: dict[str, ApprovalRequest] = {}
        self._futures: dict[str, asyncio.Future[ApprovalDecision]] = {}

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        payload: dict[str, Any] = {
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "resource": request.resource,
            "action": request.action,
            "reason": request.reason,
            "approvers": request.approvers,
            "policy_name": request.policy_name,
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    self._webhook_url,
                    json=payload,
                    headers=self._headers,
                    timeout=10.0,
                )
                resp.raise_for_status()
        except Exception:
            logger.exception("Failed to POST approval request to %s", self._webhook_url)
            request.status = ApprovalStatus.DENIED
            return ApprovalDecision(
                request_id=request.request_id,
                approved=False,
                decided_by=self._decided_by,
                reason="webhook delivery failed",
            )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[ApprovalDecision] = loop.create_future()
        self._pending[request.request_id] = request
        self._futures[request.request_id] = future

        try:
            decision = await asyncio.wait_for(future, timeout=request.timeout_seconds)
            request.status = ApprovalStatus.APPROVED if decision.approved else ApprovalStatus.DENIED
            return decision
        except TimeoutError:
            request.status = ApprovalStatus.TIMED_OUT
            return ApprovalDecision(
                request_id=request.request_id,
                approved=False,
                decided_by=self._decided_by,
                reason="timed out",
            )
        finally:
            self._pending.pop(request.request_id, None)
            self._futures.pop(request.request_id, None)

    async def list_pending(self) -> list[ApprovalRequest]:
        return list(self._pending.values())

    async def decide(self, request_id: str, decision: ApprovalDecision) -> None:
        future = self._futures.get(request_id)
        if future is not None and not future.done():
            future.set_result(decision)
