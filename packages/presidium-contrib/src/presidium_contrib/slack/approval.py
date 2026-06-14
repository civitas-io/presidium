"""SlackApprovalService — approval requests via Slack messages with buttons."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from presidium.model import ApprovalDecision, ApprovalRequest, ApprovalStatus

logger = logging.getLogger(__name__)


class SlackApprovalService:
    """Posts approval requests to a Slack channel with approve/deny buttons.

    On REQUIRE_APPROVAL, sends a Block Kit message to the configured
    channel. Then waits for a call to ``decide()`` (typically from a
    Slack interactivity webhook handler). Fail-closed on timeout.

    The ``request_id`` is included in the Slack block action values
    so the webhook handler can map button clicks back to ``decide()``.
    """

    def __init__(
        self,
        token: str,
        channel: str,
        *,
        timeout_seconds: float = 300.0,
        decided_by: str = "slack",
    ) -> None:
        self._client = AsyncWebClient(token=token)
        self._channel = channel
        self._timeout = timeout_seconds
        self._decided_by = decided_by
        self._pending: dict[str, ApprovalRequest] = {}
        self._futures: dict[str, asyncio.Future[ApprovalDecision]] = {}

    def _build_blocks(self, request: ApprovalRequest) -> list[dict[str, Any]]:
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*Approval Required*\n"
                        f"Agent: `{request.agent_id}`\n"
                        f"Action: `{request.action}` on `{request.resource}`\n"
                        f"Policy: `{request.policy_name}`\n"
                        f"Reason: {request.reason}"
                    ),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "presidium_approve",
                        "value": request.request_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Deny"},
                        "style": "danger",
                        "action_id": "presidium_deny",
                        "value": request.request_id,
                    },
                ],
            },
        ]

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        try:
            await self._client.chat_postMessage(
                channel=self._channel,
                text=f"Approval required: {request.action} on {request.resource}",
                blocks=self._build_blocks(request),
            )
        except Exception:
            logger.exception("Failed to post approval request to Slack channel %s", self._channel)
            request.status = ApprovalStatus.DENIED
            return ApprovalDecision(
                request_id=request.request_id,
                approved=False,
                decided_by=self._decided_by,
                reason="Slack delivery failed",
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
