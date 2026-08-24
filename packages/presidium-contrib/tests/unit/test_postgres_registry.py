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
        "public_key_algorithm": r.public_key_algorithm,
        "grants": [_grant_to_dict(g) for g in r.grants],
        "trust_value": r.trust_value,
        "trust_tier": r.trust_tier.value,
        "status": r.status.value,
        "owner": r.owner,
        "parent_agent_id": r.parent_agent_id,
        "trust_ceiling": r.trust_ceiling,
        "depth": r.depth,
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
        record = _row_to_record(row)
        assert record.name == "researcher"
        assert record.agent_id == "presidium://local/researcher"
        assert record.trust_tier == TrustTier.STANDARD
        assert len(record.grants) == 1
        assert record.grants[0].id == "g1"

    def test_handles_json_string_grants(self) -> None:
        import json

        row = _make_row()
        row["grants"] = json.dumps(row["grants"])
        record = _row_to_record(row)
        assert len(record.grants) == 1

    def test_handles_string_timestamps(self) -> None:
        row = _make_row()
        row["created_at"] = "2026-06-14T12:00:00+00:00"
        row["updated_at"] = "2026-06-14T12:00:00+00:00"
        record = _row_to_record(row)
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

    async def test_verify_signature_with_real_identity(self) -> None:
        """2026-08-22 fix: verify_signature() delegates to the same shared
        presidium.identity.verify_agent_signature() every AgentRegistry
        backend uses -- proven here with a real Ed25519 keypair, not a mock.
        """
        from civitas.security.identity import AgentIdentity

        identity = AgentIdentity.generate("researcher")
        record = _make_record()
        record.public_key = identity.public_key_b64()
        row = _make_row(record)

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = row
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)

        data = b"approve production deploy"
        signature = identity.sign(data)

        assert await reg.verify_signature("researcher", data, signature) is True
        assert await reg.verify_signature("researcher", b"different data", signature) is False

    async def test_verify_signature_unknown_agent_returns_false(self) -> None:
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)

        assert await reg.verify_signature("ghost", b"data", b"sig") is False

    async def test_update_identity_persists_new_key_and_algorithm(self) -> None:
        """Real proof update_identity()'s UPDATE statement actually includes
        public_key/public_key_algorithm -- a real bug (found and fixed
        alongside SqliteRegistry's identical one) where _save()'s shared
        UPDATE statement omitted them entirely, silently no-op'ing any
        change to a record's identity.
        """
        record = _make_record()
        before_row = _make_row(record)
        after_record = _make_record()
        after_record.public_key = "new-ec-p256-key"
        after_record.public_key_algorithm = "ec_p256"
        after_row = _make_row(after_record)

        mock_conn = AsyncMock()
        mock_conn.fetchrow.side_effect = [before_row, after_row]
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)

        updated = await reg.update_identity("researcher", "new-ec-p256-key", "ec_p256")

        assert updated.public_key == "new-ec-p256-key"
        assert updated.public_key_algorithm == "ec_p256"
        # The real UPDATE call itself carries the new key/algorithm as its
        # first two positional params, per _save()'s own SET clause order.
        execute_call = mock_conn.execute.call_args
        assert execute_call.args[1] == "new-ec-p256-key"
        assert execute_call.args[2] == "ec_p256"

    async def test_update_identity_unknown_agent_raises(self) -> None:
        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)

        with pytest.raises(AgentNotFoundError):
            await reg.update_identity("ghost", "some-key")


class TestPostgresLineage:
    """Trust ceiling propagation and monotonic capability narrowing
    (2026-08-22), mocked at the asyncpg boundary like the rest of this file
    -- verifies PostgresAgentRegistry follows the exact same real,
    shared presidium.lineage functions as InMemoryRegistry/SqliteRegistry,
    not a divergent reimplementation."""

    async def test_register_computes_child_ceiling_from_parent(self) -> None:
        parent = _make_record(name="orchestrator", trust_value=0.1)
        parent_row = _make_row(parent)

        child = _make_record(
            name="fresh-replacement", agent_id="presidium://local/fresh-replacement"
        )
        child.parent_agent_id = parent.agent_id
        child.trust_value = 0.7  # optimistic cold start, requested by the caller
        child.trust_ceiling = 0.1  # what register() should have computed
        child.depth = 1
        child_row_after_insert = _make_row(child)

        mock_conn = AsyncMock()
        mock_conn.fetchrow.side_effect = [parent_row, child_row_after_insert]
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)

        to_register = _make_record(
            name="fresh-replacement", agent_id="presidium://local/fresh-replacement"
        )
        to_register.parent_agent_id = parent.agent_id
        to_register.trust_value = 0.7

        result = await reg.register(to_register)

        # register() mutates the record in place before persisting -- the
        # real trust-washing attack this closes: a degraded parent (0.1)
        # cannot produce a fresh, fully-trusted child.
        assert to_register.trust_ceiling == pytest.approx(0.1)
        assert to_register.trust_value <= 0.1 + 1e-9
        assert to_register.depth == 1
        assert result.name == "fresh-replacement"

    async def test_register_rejects_dangling_parent(self) -> None:
        from presidium.errors import UnresolvableParentError

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = None  # parent lookup finds nothing
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)

        child = _make_record()
        child.parent_agent_id = "presidium://local/ghost"

        with pytest.raises(UnresolvableParentError, match="presidium://local/ghost"):
            await reg.register(child)

    async def test_register_rejects_grant_escalation(self) -> None:
        from presidium.errors import GrantEscalationError

        parent = _make_record(name="orchestrator")
        parent.grants = [Grant(resources=["tool:read_db"], actions=["read"], id="p1")]
        parent_row = _make_row(parent)

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = parent_row
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)

        child = _make_record(name="rogue-child", agent_id="presidium://local/rogue-child")
        child.parent_agent_id = parent.agent_id
        child.grants = [
            Grant(resources=["tool:admin_delete_everything"], actions=["invoke"], id="c1")
        ]

        with pytest.raises(GrantEscalationError, match="tool:admin_delete_everything"):
            await reg.register(child)

    async def test_add_grant_rejects_escalation_against_resolved_parent(self) -> None:
        from presidium.errors import GrantEscalationError

        parent = _make_record(name="orchestrator")
        child = _make_record(name="child", agent_id="presidium://local/child")
        child.parent_agent_id = parent.agent_id

        mock_conn = AsyncMock()
        # add_grant(): lookup(child) then, since parent_agent_id is set,
        # lookup_by_id(parent) -- both go through the same fetchrow mock.
        mock_conn.fetchrow.side_effect = [_make_row(child), _make_row(parent)]
        reg = PostgresAgentRegistry("postgresql://localhost/test")
        reg._pool = _mock_pool(mock_conn)

        with pytest.raises(GrantEscalationError):
            await reg.add_grant("child", Grant(resources=["tool:admin"], actions=["invoke"]))

    async def test_max_delegation_depth_configurable(self) -> None:
        from presidium.errors import DelegationDepthExceededError

        parent = _make_record(name="parent")
        parent.depth = 1
        parent_row = _make_row(parent)

        mock_conn = AsyncMock()
        mock_conn.fetchrow.return_value = parent_row
        reg = PostgresAgentRegistry("postgresql://localhost/test", max_delegation_depth=1)
        reg._pool = _mock_pool(mock_conn)

        child = _make_record(name="child", agent_id="presidium://local/child")
        child.parent_agent_id = parent.agent_id

        with pytest.raises(DelegationDepthExceededError):
            await reg.register(child)
