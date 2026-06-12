"""Presidium — governance interfaces and defaults for AI agent systems."""

from __future__ import annotations

from presidium.approval import ApprovalService, CallbackApprovalProvider
from presidium.audit import AuditEnricher, InProcessAuditEnricher
from presidium.credentials import (
    CredentialProvider,
    EnvCredentialProvider,
    FileCredentialProvider,
)
from presidium.errors import (
    AgentNotFoundError,
    ApprovalTimeoutError,
    CredentialAccessDenied,
    GrantNotFoundError,
    PolicyCompilationError,
    PolicyDeniedError,
    PolicyEvaluationError,
    PresidiumError,
    RegistryError,
)
from presidium.model import (
    ActionRequest,
    AgentRecord,
    AgentStatus,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    EnforcementMode,
    EvaluationContext,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyResult,
    PolicyRule,
    TrustEvent,
    TrustTier,
)
from presidium.policy._base import PolicyEngine
from presidium.policy.cel import CelPolicyEngine
from presidium.providers.model import GovernedModelProvider
from presidium.providers.tool import GovernedToolProvider
from presidium.registry._base import AgentRegistry
from presidium.registry.memory import InMemoryRegistry
from presidium.trust import LinearTrustScore, TrustScorer

__all__ = [
    # Enums
    "AgentStatus",
    "ApprovalStatus",
    "EnforcementMode",
    "EvaluationStage",
    "PolicyDecision",
    "TrustEvent",
    "TrustTier",
    # Data model
    "ActionRequest",
    "AgentRecord",
    "ApprovalDecision",
    "ApprovalRequest",
    "EvaluationContext",
    "Grant",
    "PolicyResult",
    "PolicyRule",
    # Protocols
    "AgentRegistry",
    "ApprovalService",
    "AuditEnricher",
    "CredentialProvider",
    "PolicyEngine",
    "TrustScorer",
    # Implementations
    "CallbackApprovalProvider",
    "CelPolicyEngine",
    "InProcessAuditEnricher",
    "EnvCredentialProvider",
    "FileCredentialProvider",
    "GovernedModelProvider",
    "GovernedToolProvider",
    "InMemoryRegistry",
    "LinearTrustScore",
    # Errors
    "AgentNotFoundError",
    "ApprovalTimeoutError",
    "CredentialAccessDenied",
    "GrantNotFoundError",
    "PolicyCompilationError",
    "PolicyDeniedError",
    "PolicyEvaluationError",
    "PresidiumError",
    "RegistryError",
]
