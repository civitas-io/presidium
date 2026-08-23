"""Delegation lineage: trust ceiling propagation and monotonic capability
narrowing across spawned/delegated agents.

Surfaced by a direct comparison against Microsoft's Agent Governance
Toolkit (``microsoft/agent-governance-toolkit``). Before this module,
``AgentRecord.parent_agent_id`` was pure metadata -- set but never
validated against anything. A caller could register a "child" agent with
a fresh, optimistic trust value and a broader grant set than its own
parent, regardless of the parent's actual (possibly degraded) trust
standing. These are pure, backend-agnostic functions: every
``AgentRegistry`` implementation calls them from ``register()``/
``add_grant()`` after resolving ``parent_agent_id`` itself, so the checks
apply uniformly across ``InMemoryRegistry``, ``SqliteRegistry``, and
``PostgresAgentRegistry`` -- not just to callers who opt into a
convenience helper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from presidium.errors import DelegationDepthExceededError, GrantEscalationError

if TYPE_CHECKING:
    from presidium.model import AgentRecord, Grant

DEFAULT_MAX_DELEGATION_DEPTH = 10
"""Matches AGT's own (`microsoft/agent-governance-toolkit`) default depth
limit for a delegation/spawn chain -- reused rather than inventing a new
number without justification."""


def compute_child_ceiling(parent: AgentRecord, requested_ceiling: float | None) -> float:
    """Compute the effective trust ceiling for a child of ``parent``.

    ``min(requested_ceiling or 1.0, parent.trust_ceiling or 1.0, parent.trust_value)``
    -- a child can never be assigned a ceiling above its parent's own
    ceiling, nor above the parent's *current* trust value. Naturally
    transitive across a multi-hop delegation chain: each hop only ever
    needs to look at its immediate parent's already-computed, already-
    persisted ``trust_ceiling``/``trust_value``, since those already
    reflect every ancestor above it.

    This is a one-time snapshot computed at registration time, not a
    continuously re-derived value -- if the parent's trust later drops
    further, the child's ceiling does not retroactively drop. AGT's own
    spec only requires the invariant ``child_ceiling <= parent_ceiling``
    at creation time; live-tracking would need cross-registry background
    reconciliation for a benefit the spec doesn't actually call for.
    """
    bounds = [
        requested_ceiling if requested_ceiling is not None else 1.0,
        parent.trust_ceiling if parent.trust_ceiling is not None else 1.0,
        parent.trust_value,
    ]
    return max(0.0, min(bounds))


def validate_grant_narrowing(
    parent: AgentRecord, child_name: str, child_grants: list[Grant]
) -> None:
    """Reject ``child_grants`` if any (resource, action) pair isn't held by
    ``parent``.

    Presidium's grant model has no wildcard concept (``has_grant()`` is
    exact list membership), so AGT's "reject wildcard delegation" rule is
    moot here -- this checks the union of (resource, action) pairs granted
    to the child is a subset of the parent's. Deliberately does NOT compare
    ``scope``/``condition``/``expires_at`` narrowing: proving a CEL
    condition string is "narrower" than another is undecidable in general
    for arbitrary expressions -- a documented non-goal, not an oversight.

    Unlike trust (a number that can be safely clamped to a valid value), a
    grant is binary -- there's no safe way to "narrow" an over-broad grant
    automatically, so this raises ``GrantEscalationError`` rather than
    silently adjusting anything.
    """
    parent_pairs: set[tuple[str, str]] = {
        (resource, action)
        for g in parent.grants
        for resource in g.resources
        for action in g.actions
    }
    child_pairs: set[tuple[str, str]] = {
        (resource, action) for g in child_grants for resource in g.resources for action in g.actions
    }
    excess = child_pairs - parent_pairs
    if excess:
        excess_str = [f"{resource}:{action}" for resource, action in sorted(excess)]
        raise GrantEscalationError(
            agent_name=child_name,
            parent_name=parent.name,
            excess=excess_str,
        )


def compute_child_depth(
    parent: AgentRecord, child_name: str, max_depth: int = DEFAULT_MAX_DELEGATION_DEPTH
) -> int:
    """Compute ``parent.depth + 1``, raising ``DelegationDepthExceededError``
    if that would exceed ``max_depth``.

    Stored, inherited-at-registration-time, like ``trust_ceiling`` -- far
    cheaper than walking the full ``parent_agent_id`` chain on every
    registration, and each hop only needs its immediate parent's
    already-computed depth.
    """
    depth = parent.depth + 1
    if depth > max_depth:
        raise DelegationDepthExceededError(agent_name=child_name, depth=depth, max_depth=max_depth)
    return depth
