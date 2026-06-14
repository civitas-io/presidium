from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from presidium.errors import AgentNotFoundError
from presidium.model import AgentRecord, Grant, TrustTier
from presidium_contrib.registry.postgres import (
    PostgresAgentRegistry,
    _grant_to_dict,
    _row_to_record,
)


def _make_record(
    name: str = "researcher",
    agent_id: str = "presidium://local/researcher",
    trust_value: float = 0.5,
) -> AgentRecord:
    return AgentRecord(
        agent_id=agent_id,
        name=name,
        public_key="dGVzdC1rZXk=",
        trust_value=trust_value,
        grants=[Grant(resources=["tool:database"], actions=["read"], id="g1")],
        owner="alice@acme.com",
    )


def _make_row(record: AgentRecord | None = None) -> dict[str, object]:
    r = record or _make_record()
    return {
        "agent_id": r.agent_id,
        "name": r.name,
        "public_key": r.public_key,
        "grants": [_grant_to_dict(g) for g in r.grants],
        "trust_value": r.trust_value,
        "trust_tier": r.trust_tier.value,
        "status": r.status.value,
        "owner": r.owner,
        "parent_agent_id": r.parent_agent_id,
        "description": r.description,
        "agent_version": r.agent_version,
        "capabilities": r.capabilities,
        "metadata": r.metadata,
        "revision": r.revision,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


class TestGrantToDict:
    def test_minimal_grant(self) -> None:
        g = Grant(resources=["tool:db"], actions=["read"], id="g1")
        d = _grant_to_dict(g)
        assert d["resources"] == ["tool:db"]
        assert d["id"] == "g1"
        assert "condition" not in d
        assert "expires_at" not in d

    def test_full_grant(self) -> None:
        exp = datetime(2026, 12, 31, tzinfo=UTC)
        g = Grant(
            resources=["tool:db"],
            actions=["read"],
            scope={"env": "prod"},
            condition="agent.trust.value >= 0.7",
            expires_at=exp,
            id="g2",
        )
        d = _grant_to_dict(g)
        assert d["condition"] == "agent.trust.value >= 0.7"
        assert d["expires_at"] == exp.isoformat()
        assert d["scope"] == {"env": "prod"}


class TestRowToRecord:
    def test_converts_row_to_agent_record(self) -> None:
        row = _make_row()
        record = _row_to_record(row)  # type: ignore[arg-type]
        assert record.name == "researcher"
        assert record.agent_id == "presidium://local/researcher"
        assert record.trust_tier == TrustTier.STANDARD
        assert len(record.grants) == 1
        assert record.grants[0].id == "g1"

    def test_handles_json_string_grants(self) -> None:
        import json

        row = _make_row()
        row["grants"] = json.dumps(row["grants"])  # type: ignore[arg-type]
        record = _row_to_record(row)  # type: ignore[arg-type]
        assert len(record.grants) == 1

    def test_handles_string_timestamps(self) -> None:
        row = _make_row()
        row["created_at"] = "2026-06-14T12:00:00+00:00"
        row["updated_at"] = "2026-06-14T12:00:00+00:00"
        record = _row_to_record(row)  # type: ignore[arg-type]
        assert isinstance(record.created_at, datetime)


class TestPostgresAgentRegistryNotConnected:
    async def test_raises_when_not_connected(self) -> None:
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        with pytest.raises(RuntimeError, match="not connected"):
            await reg.lookup("test")


def _mock_pool(conn: AsyncMock | None = None) -> MagicMock:
    mock_conn = conn or AsyncMock()

    class _AcquireCtx:
        async def __aenter__(self) -> AsyncMock:
            return mock_conn

        async def __aexit__(self, *args: object) -> None:
            pass

    pool = MagicMock()
    pool.acquire.return_value = _AcquireCtx()
    pool.close = AsyncMock()
    return pool


class TestPostgresAgentRegistryWithMock:
    async def test_lookup_returns_none_when_not_found(self) -> None:
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)
        result = await reg.lookup("ghost")
        assert result is None

    async def test_deregister_nonexistent_raises(self) -> None:
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)
        with pytest.raises(AgentNotFoundError):
            await reg.deregister("ghost")

    async def test_has_grant_nonexistent_raises(self) -> None:
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)
        with pytest.raises(AgentNotFoundError):
            await reg.has_grant("ghost", "tool:db", "read")

    async def test_close(self) -> None:
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        pool = _mock_pool()
        reg._pool = pool
        await reg.close()
        pool.close.assert_called_once()
        assert reg._pool is None
