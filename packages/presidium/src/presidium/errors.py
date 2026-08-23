"""Presidium error hierarchy.

All Presidium exceptions inherit from PresidiumError. External exceptions
(e.g. cel-python errors) are wrapped at package boundaries.
"""

from __future__ import annotations


class PresidiumError(Exception):
    """Base exception for all Presidium errors."""


class PolicyEvaluationError(PresidiumError):
    """Raised when a CEL expression fails to evaluate."""

    def __init__(self, policy_name: str, detail: str) -> None:
        self.policy_name = policy_name
        self.detail = detail
        super().__init__(f"Policy '{policy_name}' evaluation failed: {detail}")


class PolicyCompilationError(PresidiumError):
    """Raised when a CEL expression fails to compile at load time."""

    def __init__(self, policy_name: str, expression: str, detail: str) -> None:
        self.policy_name = policy_name
        self.expression = expression
        self.detail = detail
        super().__init__(
            f"Policy '{policy_name}' compilation failed: {detail} (expression: {expression!r})"
        )


class PolicyDeniedError(PresidiumError):
    """Raised by enforcement points when a policy denies an action."""

    def __init__(self, reason: str | None, policy_name: str | None = None) -> None:
        self.reason = reason
        self.policy_name = policy_name
        msg = f"Action denied by policy '{policy_name}': {reason}" if policy_name else reason or ""
        super().__init__(msg)


class RegistryError(PresidiumError):
    """Raised for agent registry operations."""


class AgentNotFoundError(RegistryError):
    """Raised when a lookup finds no matching agent."""

    def __init__(self, name: str) -> None:
        self.agent_name = name
        super().__init__(f"Agent not found: {name!r}")


class GrantNotFoundError(RegistryError):
    """Raised when a grant removal targets a non-existent grant ID."""

    def __init__(self, agent_name: str, grant_id: str) -> None:
        self.agent_name = agent_name
        self.grant_id = grant_id
        super().__init__(f"Grant {grant_id!r} not found on agent {agent_name!r}")


class UnresolvableParentError(RegistryError):
    """Raised when ``AgentRecord.parent_agent_id`` is set but does not resolve
    to a real, registered agent. Lineage-derived checks (trust ceiling,
    capability narrowing, delegation depth) all require a real parent to
    validate against — a dangling ``parent_agent_id`` is treated as invalid
    input, not silently ignored, since silently ignoring it would reopen the
    exact bypass these checks exist to close."""

    def __init__(self, parent_agent_id: str) -> None:
        self.parent_agent_id = parent_agent_id
        super().__init__(
            f"parent_agent_id {parent_agent_id!r} does not resolve to a registered agent"
        )


class GrantEscalationError(RegistryError):
    """Raised when a child agent's grants are not a subset of its resolved
    parent's grants (monotonic capability narrowing, AGT-comparison finding).
    Unlike trust, a grant cannot be safely clamped to a valid value — it is
    binary, so an escalation attempt is rejected outright rather than
    silently narrowed."""

    def __init__(self, agent_name: str, parent_name: str, excess: list[str]) -> None:
        self.agent_name = agent_name
        self.parent_name = parent_name
        self.excess = excess
        super().__init__(
            f"Agent {agent_name!r} requests grants not held by parent {parent_name!r}: {excess}"
        )


class DelegationDepthExceededError(RegistryError):
    """Raised when registering an agent would exceed the registry's
    configured ``max_delegation_depth`` (default 10, matching AGT's own
    precedent) — bounds how deep a spawn/delegation chain may go."""

    def __init__(self, agent_name: str, depth: int, max_depth: int) -> None:
        self.agent_name = agent_name
        self.depth = depth
        self.max_depth = max_depth
        super().__init__(
            f"Agent {agent_name!r} at depth {depth} exceeds max_delegation_depth={max_depth}"
        )


class CredentialAccessDenied(PresidiumError):
    """Raised when an agent lacks a grant for a credential."""

    def __init__(self, agent_id: str, credential_name: str) -> None:
        self.agent_id = agent_id
        self.credential_name = credential_name
        super().__init__(f"Agent {agent_id!r} lacks a grant for credential:{credential_name}")


class ApprovalTimeoutError(PresidiumError):
    """Raised when an approval request times out."""

    def __init__(self, request_id: str, timeout_seconds: float) -> None:
        self.request_id = request_id
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Approval request {request_id!r} timed out after {timeout_seconds}s")


# ---------------------------------------------------------------------------
# Trust scoring errors (FR-E.1, FR-E.2)
# ---------------------------------------------------------------------------


class TrustScoringError(PresidiumError):
    """Base exception for trust scoring operations."""


class SpecMismatchError(TrustScoringError):
    """Raised when a scorer's current spec_hash doesn't match the pinned hash (FR-E.1)."""

    def __init__(self, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"Spec hash mismatch: pinned={expected[:12]}… current={actual[:12]}…")


class MissingAttributionError(TrustScoringError):
    """Raised when a HUMAN_OVERRIDE event lacks a required actor_id (FR-E.2)."""

    def __init__(self) -> None:
        super().__init__(
            "HUMAN_OVERRIDE events require actor_id in EventContext for audit attribution"
        )
