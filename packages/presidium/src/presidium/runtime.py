"""GovernedRuntime — governance-wrapped Civitas runtime."""

from __future__ import annotations

from presidium.approval import ApprovalService, CallbackApprovalProvider
from presidium.audit import AuditSink, InProcessAuditEnricher
from presidium.policy._base import PolicyEngine
from presidium.policy.cel import CelPolicyEngine
from presidium.providers.model import GovernedModelProvider
from presidium.providers.tool import GovernedToolProvider
from presidium.registry._base import AgentRegistry
from presidium.registry.memory import InMemoryRegistry


class GovernedRuntime:
    """Governance layer wrapping a Civitas Runtime.

    Programmatic constructor wires governance components together:
    registry, policy engine, credential provider, approval service,
    audit enricher, and governed providers.

    ``from_config()`` (YAML-based) is deferred until Civitas exposes
    ``Runtime.from_config_dict()``.
    """

    def __init__(
        self,
        *,
        registry: AgentRegistry | None = None,
        engine: PolicyEngine | None = None,
        approval: ApprovalService | None = None,
        audit_sink: AuditSink | None = None,
    ) -> None:
        self.registry: AgentRegistry = registry or InMemoryRegistry()
        self.engine: PolicyEngine = engine or CelPolicyEngine()
        self.approval: ApprovalService = approval or CallbackApprovalProvider()

        self.audit_enricher: InProcessAuditEnricher | None = None
        if audit_sink is not None:
            self.audit_enricher = InProcessAuditEnricher(audit_sink, self.registry)

        self.model_provider = GovernedModelProvider(
            engine=self.engine,
            registry=self.registry,
            approval=self.approval,
            audit_sink=self.audit_enricher,
        )

        self.tool_provider = GovernedToolProvider(
            engine=self.engine,
            registry=self.registry,
            approval=self.approval,
            audit_sink=self.audit_enricher,
        )
