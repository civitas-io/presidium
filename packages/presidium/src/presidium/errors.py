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
