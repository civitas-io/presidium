"""JSON (de)serialization for AgentRecord/Grant at the M7 network boundary.

Deliberately lives in presidium-contrib, not presidium core: `presidium.model` stays pure
dataclasses/enums (no JSON concerns baked in), matching this codebase's own established
"translation lives at the boundary" layering. No (de)serialization helper existed on
AgentRecord/Grant before this -- built from scratch here, not adapted from an existing one.
"""

from __future__ import annotations

from typing import Any

from presidium.model import AgentRecord, Grant

#: Fields a caller MAY set at registration time over HTTP. Deliberately excludes grants,
#: trust_value, status, revision, created_at, updated_at, depth -- these are either managed
#: internally (revision/timestamps/depth), start at a fixed default (status, trust_value), or
#: belong to a real, separate, not-yet-built grant-management endpoint (grants) -- a network
#: caller should never be able to set them directly via a raw registration POST.
_REGISTER_REQUIRED_FIELDS = ("agent_id", "name", "public_key")
_REGISTER_OPTIONAL_FIELDS = (
    "public_key_algorithm",
    "owner",
    "description",
    "agent_version",
    "capabilities",
    "metadata",
    "parent_agent_id",
    "trust_ceiling",
)


class RegistrationRequestError(ValueError):
    """Raised for a malformed registration request body -- caught by the calling GenServer and
    turned into a real, JSON-level ``{"status": "error", ...}`` reply (never a raised
    exception across the network boundary, matching this milestone's own NFR-1).
    """


def agent_record_from_register_request(body: dict[str, Any]) -> AgentRecord:
    """Build a real AgentRecord from a POST /v1/agents request body.

    Raises RegistrationRequestError (never a bare KeyError/TypeError) for a missing required
    field or a wrong-typed value -- the caller (RegisterAgentGatewayAgent) catches this and
    replies with a real, honest {"status": "error", ...} over HTTP 200, per this milestone's
    established never-raise-across-the-network-boundary convention.
    """
    missing = [f for f in _REGISTER_REQUIRED_FIELDS if f not in body]
    if missing:
        raise RegistrationRequestError(f"Missing required field(s): {', '.join(missing)}")

    kwargs: dict[str, Any] = {f: body[f] for f in _REGISTER_REQUIRED_FIELDS}
    for f in _REGISTER_OPTIONAL_FIELDS:
        if f in body:
            kwargs[f] = body[f]

    try:
        return AgentRecord(**kwargs)
    except TypeError as exc:  # pragma: no cover
        # Real, honest defensive-only branch: AgentRecord has no __post_init__ validation
        # (confirmed directly -- dataclass fields aren't runtime type-checked), and every name
        # copied into kwargs above comes from the fixed _REGISTER_*_FIELDS allow-lists, each
        # verified to match a real AgentRecord field -- so this can't currently be reached by
        # any real client input. Kept as a safety net against that allow-list drifting out of
        # sync with AgentRecord's real fields in the future, not because it's reachable today.
        raise RegistrationRequestError(f"Invalid registration request: {exc}") from exc


def agent_record_to_dict(record: AgentRecord) -> dict[str, Any]:
    """Serialize a real AgentRecord to a JSON-safe dict -- enums as their string values,
    datetimes as ISO 8601, Grant instances as nested dicts. Covers every field (not just the
    registrable subset) since a real, existing agent may carry grants/trust history/lineage
    this HTTP layer's own register endpoint never set directly (e.g. added via a separate,
    in-process admin script).
    """
    return {
        "agent_id": record.agent_id,
        "name": record.name,
        "public_key": record.public_key,
        "public_key_algorithm": record.public_key_algorithm,
        "grants": [_grant_to_dict(g) for g in record.grants],
        "trust_value": record.trust_value,
        "trust_tier": record.trust_tier.value,
        "status": record.status.value,
        "owner": record.owner,
        "parent_agent_id": record.parent_agent_id,
        "trust_ceiling": record.trust_ceiling,
        "depth": record.depth,
        "description": record.description,
        "agent_version": record.agent_version,
        "capabilities": list(record.capabilities),
        "metadata": dict(record.metadata),
        "revision": record.revision,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def _grant_to_dict(grant: Grant) -> dict[str, Any]:
    return {
        "id": grant.id,
        "resources": list(grant.resources),
        "actions": list(grant.actions),
        "scope": dict(grant.scope),
        "condition": grant.condition,
        "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
    }
