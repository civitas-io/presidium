"""ApprovalService Protocol and CallbackApprovalProvider."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from presidium.model import ApprovalDecision, ApprovalRequest, ApprovalStatus

logger = logging.getLogger(__name__)

ApprovalCallback = Callable[[ApprovalRequest], Awaitable[ApprovalDecision]]


@runtime_checkable
class ApprovalService(Protocol):
    """Protocol for human-in-the-loop approval of governed actions."""

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision: ...

    async def list_pending(self) -> list[ApprovalRequest]: ...

    async def decide(self, request_id: str, decision: ApprovalDecision) -> None: ...


class CallbackApprovalProvider:
    """Default ApprovalService with callback, auto-approve, and manual modes.

    Modes (checked in order):
    1. auto_approve=True → immediately approve
    2. auto_deny=True → immediately deny
    3. callback provided → call it and return the result
    4. manual mode → create an asyncio.Future, wait for decide() call or timeout

    Fail-closed: timeout auto-denies.
    """

    def __init__(
        self,
        *,
        auto_approve: bool = False,
        auto_deny: bool = False,
        callback: ApprovalCallback | None = None,
        decided_by: str = "system",
    ) -> None:
        self._auto_approve = auto_approve
        self._auto_deny = auto_deny
        self._callback = callback
        self._decided_by = decided_by
        self._pending: dict[str, ApprovalRequest] = {}
        self._futures: dict[str, asyncio.Future[ApprovalDecision]] = {}

    async def request_approval(self, request: ApprovalRequest) -> ApprovalDecision:
        if self._auto_approve:
            request.status = ApprovalStatus.APPROVED
            return ApprovalDecision(
                request_id=request.request_id,
                approved=True,
                decided_by=self._decided_by,
                reason="auto-approved",
            )

        if self._auto_deny:
            request.status = ApprovalStatus.DENIED
            return ApprovalDecision(
                request_id=request.request_id,
                approved=False,
                decided_by=self._decided_by,
                reason="auto-denied",
            )

        if self._callback is not None:
            decision = await self._callback(request)
            request.status = ApprovalStatus.APPROVED if decision.approved else ApprovalStatus.DENIED
            return decision

        # Manual mode: wait for decide() or timeout
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
