"""Presidium data model.

All shared enums and dataclasses for the governance layer. These are the
canonical types referenced by every Protocol and implementation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AgentStatus(Enum):
    """Lifecycle states for a governed agent."""

    REGISTERED = "registered"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    SUSPENDED = "suspended"


class TrustTier(Enum):
    """Trust classification tiers.

    Thresholds: TRUSTED >= 0.7, STANDARD 0.3-0.7, RESTRICTED < 0.3.
    """

    TRUSTED = "trusted"
    STANDARD = "standard"
    RESTRICTED = "restricted"


class TrustEvent(Enum):
    """Events that affect an agent's trust score."""

    SUCCESS = "success"
    FAILURE = "failure"
    POLICY_VIOLATION = "policy_violation"
    HUMAN_OVERRIDE = "human_override"


class PolicyDecision(Enum):
    """Possible outcomes of a policy evaluation."""

    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class EvaluationStage(Enum):
    """Points in the agent lifecycle where policies are evaluated."""

    PRE_TOOL = "pre_tool"
    PRE_LLM = "pre_llm"
    REGISTRATION = "registration"


class EnforcementMode(Enum):
    """How strictly a policy decision is enforced.

    ADVISORY: log only, never block.
    SOFT: log + warn, don't block.
    HARD: enforce — block on DENY.
    """

    ADVISORY = "advisory"
    SOFT = "soft"
    HARD = "hard"


class ApprovalStatus(Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMED_OUT = "timed_out"


# ---------------------------------------------------------------------------
# Dataclasses — Agent Identity & Governance
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(UTC)


def _generate_grant_id() -> str:
    """Generate a stable grant identifier."""
    return str(uuid.uuid4())


@dataclass
class Grant:
    """A structured authorization grant held by an agent.

    Grants are data — the CEL policy engine evaluates them.
    Grants are NOT policies — policies decide whether to honour grants.
    """

    resources: list[str]
    """Resource identifiers, e.g. ["tool:database", "llm:claude-sonnet"]."""

    actions: list[str]
    """Permitted actions, e.g. ["read", "write", "invoke"]."""

    scope: dict[str, str] = field(default_factory=dict)
    """Optional scope constraints, e.g. {"environment": "prod"}."""

    condition: str | None = None
    """CEL expression evaluated at policy time, e.g. "agent.trust.value >= 0.7"."""

    expires_at: datetime | None = None
    """When this grant expires. None means no expiry."""

    id: str = field(default_factory=_generate_grant_id)
    """Stable identifier for grant management (add/remove). Auto-generated UUID."""


@dataclass
class AgentRecord:
    """Identity and governance metadata for a registered agent."""

    # Identity
    agent_id: str
    """SPIFFE-compatible URI: presidium://{trust_domain}/{path}."""

    name: str
    """Short name for Civitas message routing."""

    public_key: str
    """Ed25519 public key (base64) — cryptographic identity binding."""

    # Governance
    grants: list[Grant] = field(default_factory=list)
    trust_value: float = 0.5
    trust_tier: TrustTier = TrustTier.STANDARD
    status: AgentStatus = AgentStatus.REGISTERED

    # Accountability
    owner: str | None = None
    """Human sponsor email/ID."""

    # Lineage
    parent_agent_id: str | None = None
    """Parent agent ID if dynamically spawned."""

    # Metadata
    description: str | None = None
    agent_version: str | None = None
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Lifecycle
    revision: int = 0
    """Monotonic counter, incremented on every mutation."""

    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Dataclasses — Policy Engine
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PolicyRule:
    """A single policy rule with a CEL expression."""

    name: str
    stage: EvaluationStage | list[EvaluationStage]
    """Single stage or list of stages this rule applies to."""

    expression: str
    """CEL expression. Evaluated against the EvaluationContext."""

    decision: PolicyDecision
    """What to return if the expression evaluates to true."""

    reason: str | None = None
    description: str | None = None
    priority: int = 0
    """Higher priority = evaluated first."""

    enforcement: EnforcementMode = EnforcementMode.HARD
    approvers: tuple[str, ...] = ()
    """For REQUIRE_APPROVAL decisions. Tuple for frozen dataclass compatibility."""

    enabled: bool = True


@dataclass
class PolicyResult:
    """Result of a policy evaluation."""

    decision: PolicyDecision
    policy_name: str | None = None
    """None when no rule matched (all passed)."""

    reason: str | None = None
    approvers: list[str] | None = None
    enforcement: EnforcementMode = EnforcementMode.HARD


@dataclass
class ActionRequest:
    """What the agent is attempting to do."""

    resource: str
    """E.g. "tool:database", "llm:claude-sonnet", "agent:writer"."""

    action: str
    """E.g. "read", "write", "invoke", "send"."""

    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationContext:
    """Full context passed to the policy engine for evaluation."""

    agent: AgentRecord
    request: ActionRequest
    time: datetime


# ---------------------------------------------------------------------------
# Dataclasses — Approval Service
# ---------------------------------------------------------------------------


@dataclass
class ApprovalRequest:
    """A request for human approval of a governed action."""

    request_id: str
    agent_id: str
    """presidium:// URI."""

    resource: str
    action: str
    reason: str
    """From PolicyResult.reason."""

    approvers: list[str]
    """From PolicyRule.approvers."""

    context: dict[str, Any]
    policy_name: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    timeout_seconds: float = 300.0


@dataclass
class ApprovalDecision:
    """A decision on an approval request."""

    request_id: str
    approved: bool
    decided_by: str
    reason: str | None = None
