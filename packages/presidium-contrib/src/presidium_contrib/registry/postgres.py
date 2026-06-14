"""PostgresAgentRegistry — production-grade async PostgreSQL registry."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import asyncpg

from presidium.errors import AgentNotFoundError, GrantNotFoundError
from presidium.model import AgentRecord, AgentStatus, Grant, TrustEvent, TrustTier
from presidium.trust import LinearTrustScore

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS agent_records (
    agent_id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    public_key TEXT NOT NULL,
    grants JSONB NOT NULL DEFAULT '[]',
    trust_value DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    trust_tier TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'registered',
    owner TEXT,
    parent_agent_id TEXT,
    description TEXT,
    agent_version TEXT,
    capabilities JSONB NOT NULL DEFAULT '[]',
    metadata JSONB NOT NULL DEFAULT '{}',
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS trust_events (
    id SERIAL PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES agent_records(agent_id),
    event_type TEXT NOT NULL,
    value_before DOUBLE PRECISION NOT NULL,
    value_after DOUBLE PRECISION NOT NULL,
    tier_before TEXT NOT NULL,
    tier_after TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_trust_events_agent
    ON trust_events(agent_id, timestamp);
"""


def _grant_to_dict(g: Grant) -> dict[str, Any]:
    d: dict[str, Any] = {
        "resources": g.resources,
        "actions": g.actions,
        "scope": g.scope,
        "id": g.id,
    }
    if g.condition is not None:
        d["condition"] = g.condition
    if g.expires_at is not None:
        d["expires_at"] = g.expires_at.isoformat()
    return d


def _row_to_record(row: asyncpg.Record) -> AgentRecord:
    grants_raw = json.loads(row["grants"]) if isinstance(row["grants"], str) else row["grants"]
    grants = [
        Grant(
            resources=g["resources"],
            actions=g["actions"],
            scope=g.get("scope", {}),
            condition=g.get("condition"),
            expires_at=(datetime.fromisoformat(g["expires_at"]) if g.get("expires_at") else None),
            id=g["id"],
        )
        for g in grants_raw
    ]

    caps = row["capabilities"]
    capabilities = json.loads(caps) if isinstance(caps, str) else (caps or [])

    meta = row["metadata"]
    metadata = json.loads(meta) if isinstance(meta, str) else (meta or {})

    created = row["created_at"]
    updated = row["updated_at"]

    return AgentRecord(
        agent_id=row["agent_id"],
        name=row["name"],
        public_key=row["public_key"],
        grants=grants,
        trust_value=row["trust_value"],
        trust_tier=TrustTier(row["trust_tier"]),
        status=AgentStatus(row["status"]),
        owner=row["owner"],
        parent_agent_id=row["parent_agent_id"],
        description=row["description"],
        agent_version=row["agent_version"],
        capabilities=capabilities,
        metadata=metadata,
        revision=row["revision"],
        created_at=created if isinstance(created, datetime) else datetime.fromisoformat(created),
        updated_at=updated if isinstance(updated, datetime) else datetime.fromisoformat(updated),
    )


class PostgresAgentRegistry:
    """PostgreSQL-backed agent registry for production deployments.

    Uses asyncpg for async I/O. SERIALIZABLE isolation for write
    consistency. Trust scoring delegated to in-memory LinearTrustScore.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._scorers: dict[str, LinearTrustScore] = {}
        self._write_lock = asyncio.Lock()

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn)
        async with self._pool.acquire() as conn:
            await conn.execute(_CREATE_TABLES)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    def _ensure_scorer(self, name: str, trust_value: float) -> LinearTrustScore:
        scorer = self._scorers.get(name)
        if scorer is None:
            scorer = LinearTrustScore(initial_value=trust_value)
            self._scorers[name] = scorer
        return scorer

    def _sync_trust(self, record: AgentRecord) -> None:
        scorer = self._scorers.get(record.name)
        if scorer is not None:
            record.trust_value = scorer.value
            record.trust_tier = scorer.tier

    async def _pool_or_raise(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("PostgresAgentRegistry not connected — call connect() first")
        return self._pool

    async def register(self, record: AgentRecord) -> AgentRecord:
        async with self._write_lock:
            pool = await self._pool_or_raise()
            record.revision += 1
            record.updated_at = datetime.now(UTC)
            grants_json = json.dumps([_grant_to_dict(g) for g in record.grants])
            caps_json = json.dumps(record.capabilities)
            meta_json = json.dumps(record.metadata)

            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO agent_records
                    (agent_id, name, public_key, grants, trust_value, trust_tier,
                     status, owner, parent_agent_id, description, agent_version,
                     capabilities, metadata, revision, created_at, updated_at)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                    ON CONFLICT (name) DO UPDATE SET
                     agent_id=$1, public_key=$3, grants=$4, trust_value=$5,
                     trust_tier=$6, status=$7, owner=$8, parent_agent_id=$9,
                     description=$10, agent_version=$11, capabilities=$12,
                     metadata=$13, revision=$14, updated_at=$16""",
                    record.agent_id,
                    record.name,
                    record.public_key,
                    grants_json,
                    record.trust_value,
                    record.trust_tier.value,
                    record.status.value,
                    record.owner,
                    record.parent_agent_id,
                    record.description,
                    record.agent_version,
                    caps_json,
                    meta_json,
                    record.revision,
                    record.created_at,
                    record.updated_at,
                )
            self._ensure_scorer(record.name, record.trust_value)
            return await self._lookup_internal(record.name)

    async def deregister(self, name: str) -> None:
        async with self._write_lock:
            pool = await self._pool_or_raise()
            await self._lookup_or_raise(name)
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM agent_records WHERE name = $1", name)
            self._scorers.pop(name, None)

    async def lookup(self, name: str) -> AgentRecord | None:
        pool = await self._pool_or_raise()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM agent_records WHERE name = $1", name)
        if row is None:
            return None
        record = _row_to_record(row)
        self._sync_trust(record)
        return record

    async def lookup_by_id(self, agent_id: str) -> AgentRecord | None:
        pool = await self._pool_or_raise()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM agent_records WHERE agent_id = $1", agent_id)
        if row is None:
            return None
        record = _row_to_record(row)
        self._sync_trust(record)
        return record

    async def list_agents(
        self,
        status: AgentStatus | None = None,
        trust_tier: TrustTier | None = None,
        owner: str | None = None,
    ) -> list[AgentRecord]:
        pool = await self._pool_or_raise()

        if trust_tier is not None:
            await self._sync_all_trust_to_db()

        clauses: list[str] = []
        params: list[str] = []
        idx = 1
        if status is not None:
            clauses.append(f"status = ${idx}")
            params.append(status.value)
            idx += 1
        if trust_tier is not None:
            clauses.append(f"trust_tier = ${idx}")
            params.append(trust_tier.value)
            idx += 1
        if owner is not None:
            clauses.append(f"owner = ${idx}")
            params.append(owner)
            idx += 1

        query = "SELECT * FROM agent_records"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        results = []
        for row in rows:
            record = _row_to_record(row)
            self._sync_trust(record)
            results.append(record)
        return results

    async def add_grant(self, name: str, grant: Grant) -> AgentRecord:
        async with self._write_lock:
            record = await self._lookup_or_raise(name)
            record.grants.append(grant)
            await self._save(record)
            return await self._lookup_internal(name)

    async def remove_grant(self, name: str, grant_id: str) -> AgentRecord:
        async with self._write_lock:
            record = await self._lookup_or_raise(name)
            for i, g in enumerate(record.grants):
                if g.id == grant_id:
                    record.grants.pop(i)
                    await self._save(record)
                    return await self._lookup_internal(name)
            raise GrantNotFoundError(name, grant_id)

    async def has_grant(self, name: str, resource: str, action: str) -> bool:
        record = await self._lookup_or_raise(name)
        return any(resource in g.resources and action in g.actions for g in record.grants)

    async def record_trust_event(self, name: str, event: TrustEvent) -> AgentRecord:
        async with self._write_lock:
            record = await self._lookup_or_raise(name)
            scorer = self._ensure_scorer(name, record.trust_value)

            value_before = scorer.value
            tier_before = scorer.tier
            scorer.record_event(event)
            value_after = scorer.value
            tier_after = scorer.tier

            record.trust_value = value_after
            record.trust_tier = tier_after
            await self._save(record)

            pool = await self._pool_or_raise()
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO trust_events
                    (agent_id, event_type, value_before, value_after,
                     tier_before, tier_after, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    record.agent_id,
                    event.value,
                    value_before,
                    value_after,
                    tier_before.value,
                    tier_after.value,
                    datetime.now(UTC),
                )
            return await self._lookup_internal(name)

    async def set_trust(self, name: str, value: float, reason: str) -> AgentRecord:
        async with self._write_lock:
            record = await self._lookup_or_raise(name)
            scorer = self._ensure_scorer(name, record.trust_value)

            value_before = scorer.value
            tier_before = scorer.tier
            scorer.set_value(value)
            value_after = scorer.value
            tier_after = scorer.tier

            record.trust_value = value_after
            record.trust_tier = tier_after
            await self._save(record)

            pool = await self._pool_or_raise()
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO trust_events
                    (agent_id, event_type, value_before, value_after,
                     tier_before, tier_after, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    record.agent_id,
                    TrustEvent.HUMAN_OVERRIDE.value,
                    value_before,
                    value_after,
                    tier_before.value,
                    tier_after.value,
                    datetime.now(UTC),
                )
            return await self._lookup_internal(name)

    async def update_status(self, name: str, status: AgentStatus) -> AgentRecord:
        async with self._write_lock:
            record = await self._lookup_or_raise(name)
            record.status = status
            await self._save(record)
            return await self._lookup_internal(name)

    async def _lookup_or_raise(self, name: str) -> AgentRecord:
        record = await self.lookup(name)
        if record is None:
            raise AgentNotFoundError(name)
        return record

    async def _lookup_internal(self, name: str) -> AgentRecord:
        record = await self.lookup(name)
        if record is None:
            raise AgentNotFoundError(name)
        return record

    async def _sync_all_trust_to_db(self) -> None:
        pool = await self._pool_or_raise()
        async with pool.acquire() as conn:
            for name, scorer in self._scorers.items():
                await conn.execute(
                    "UPDATE agent_records SET trust_value=$1, trust_tier=$2 WHERE name=$3",
                    scorer.value,
                    scorer.tier.value,
                    name,
                )

    async def _save(self, record: AgentRecord) -> None:
        pool = await self._pool_or_raise()
        record.revision += 1
        record.updated_at = datetime.now(UTC)
        grants_json = json.dumps([_grant_to_dict(g) for g in record.grants])
        caps_json = json.dumps(record.capabilities)
        meta_json = json.dumps(record.metadata)

        async with pool.acquire() as conn:
            await conn.execute(
                """UPDATE agent_records SET
                    grants=$1, trust_value=$2, trust_tier=$3, status=$4,
                    owner=$5, parent_agent_id=$6, description=$7,
                    agent_version=$8, capabilities=$9, metadata=$10,
                    revision=$11, updated_at=$12
                WHERE name=$13""",
                grants_json,
                record.trust_value,
                record.trust_tier.value,
                record.status.value,
                record.owner,
                record.parent_agent_id,
                record.description,
                record.agent_version,
                caps_json,
                meta_json,
                record.revision,
                record.updated_at,
                record.name,
            )
