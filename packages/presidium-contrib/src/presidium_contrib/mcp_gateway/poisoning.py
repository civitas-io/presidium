"""Tool poisoning detection via hash-based fingerprinting."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class PoisoningStatus(Enum):
    CLEAN = "clean"
    UNAPPROVED = "unapproved"
    DESCRIPTION_CHANGED = "description_changed"
    PARAMETERS_CHANGED = "parameters_changed"


@dataclass(frozen=True)
class ToolSnapshot:
    name: str
    description_hash: str
    parameters_hash: str
    approved_at: datetime
    approved_by: str


@dataclass(frozen=True)
class PoisoningResult:
    status: PoisoningStatus
    tool_name: str
    detail: str | None = None


def _hash_json(data: Any) -> str:  # noqa: ANN401
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class PoisoningDetector:
    def __init__(self) -> None:
        self._snapshots: dict[str, ToolSnapshot] = {}

    def approve_tool(
        self,
        name: str,
        description: str,
        parameters: Mapping[str, Any],
        approved_by: str,
    ) -> ToolSnapshot:
        snapshot = ToolSnapshot(
            name=name,
            description_hash=_hash_json(description),
            parameters_hash=_hash_json(dict(parameters)),
            approved_at=datetime.now(UTC),
            approved_by=approved_by,
        )
        self._snapshots[name] = snapshot
        return snapshot

    def check(
        self,
        name: str,
        description: str,
        parameters: Mapping[str, Any],
    ) -> PoisoningResult:
        snapshot = self._snapshots.get(name)
        if snapshot is None:
            return PoisoningResult(
                status=PoisoningStatus.UNAPPROVED,
                tool_name=name,
                detail="Tool has not been approved",
            )

        desc_hash = _hash_json(description)
        if desc_hash != snapshot.description_hash:
            return PoisoningResult(
                status=PoisoningStatus.DESCRIPTION_CHANGED,
                tool_name=name,
                detail=f"Description hash changed since approval on "
                f"{snapshot.approved_at.isoformat()}",
            )

        param_hash = _hash_json(dict(parameters))
        if param_hash != snapshot.parameters_hash:
            return PoisoningResult(
                status=PoisoningStatus.PARAMETERS_CHANGED,
                tool_name=name,
                detail=f"Parameters hash changed since approval on "
                f"{snapshot.approved_at.isoformat()}",
            )

        return PoisoningResult(status=PoisoningStatus.CLEAN, tool_name=name)

    def revoke(self, name: str) -> bool:
        return self._snapshots.pop(name, None) is not None
