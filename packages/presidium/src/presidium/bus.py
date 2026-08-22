"""GovernedMessageBus — PRE_MESSAGE policy enforcement on inter-agent messages."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from civitas.bus import MessageBus
from civitas.messages import Message
from civitas.observability.tracer import Tracer
from civitas.registry import Registry
from civitas.serializer import Serializer
from civitas.transport import Transport

from presidium.errors import PolicyDeniedError
from presidium.model import (
    ActionRequest,
    EvaluationContext,
    EvaluationStage,
    PolicyDecision,
)
from presidium.policy._base import PolicyEngine
from presidium.registry._base import AgentRegistry

logger = logging.getLogger(__name__)


class GovernedMessageBus(MessageBus):
    """MessageBus subclass that evaluates PRE_MESSAGE policies before routing.

    If the sender is registered in the governance registry, policies are
    evaluated. System messages (``_agency.*``) bypass policy evaluation.
    """

    def __init__(
        self,
        transport: Transport,
        registry: Registry,
        serializer: Serializer,
        tracer: Tracer,
        *,
        policy_engine: PolicyEngine,
        governance_registry: AgentRegistry,
        audit_sink: Any = None,  # noqa: ANN401
    ) -> None:
        super().__init__(transport, registry, serializer, tracer, audit_sink=audit_sink)
        self._policy_engine = policy_engine
        self._governance_registry = governance_registry

    async def route(self, message: Message) -> None:
        if not message.type.startswith("_agency."):
            await self._evaluate_pre_message(message)
        await super().route(message)

    async def _evaluate_pre_message(self, message: Message) -> None:
        record = await self._governance_registry.lookup(message.sender)
        if record is None:
            return

        context = EvaluationContext(
            agent=record,
            request=ActionRequest(
                resource=f"agent:{message.recipient}",
                action="send",
                parameters={"message_type": message.type},
            ),
            time=datetime.now(UTC),
        )
        result = await self._policy_engine.evaluate(EvaluationStage.PRE_MESSAGE, context)

        if result.decision == PolicyDecision.DENY:
            logger.warning(
                "policy.pre_message.denied sender=%s recipient=%s policy=%s",
                message.sender,
                message.recipient,
                result.policy_name,
            )
            raise PolicyDeniedError(result.reason, result.policy_name)
