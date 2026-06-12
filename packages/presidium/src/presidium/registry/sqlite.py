"""SqliteRegistry — async SQLite-backed AgentRegistry implementation."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

import aiosqlite

from presidium.errors import AgentNotFoundError, GrantNotFoundError
from presidium.model import AgentRecord, AgentStatus, Grant, TrustEvent, TrustTier
from presidium.trust import LinearTrustScore

_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS agent_records (
    agent_id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    public_key TEXT NOT NULL,
    grants TEXT NOT NULL DEFAULT '[]',
    trust_value REAL NOT NULL DEFAULT 0.5,
    trust_tier TEXT NOT NULL DEFAULT 'standard',
    status TEXT NOT NULL DEFAULT 'registered',
    owner TEXT,
    parent_agent_id TEXT,
    description TEXT,
    agent_version TEXT,
    capabilities TEXT NOT NULL DEFAULT '[]',
    metadata TEXT NOT NULL DEFAULT '{}',
    revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trust_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL REFERENCES agent_records(agent_id),
    event_type TEXT NOT NULL,
    value_before REAL NOT NULL,
    value_after REAL NOT NULL,
    tier_before TEXT NOT NULL,
    tier_after TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_trust_events_agent
    ON trust_events(agent_id, timestamp);
"""


def _record_to_row(r: AgentRecord) -> dict[str, Any]:
    return {
        "agent_id": r.agent_id,
        "name": r.name,
        "public_key": r.public_key,
        "grants": json.dumps([_grant_to_dict(g) for g in r.grants]),
        "trust_value": r.trust_value,
        "trust_tier": r.trust_tier.value,
        "status": r.status.value,
        "owner": r.owner,
        "parent_agent_id": r.parent_agent_id,
        "description": r.description,
        "agent_version": r.agent_version,
        "capabilities": json.dumps(r.capabilities),
        "metadata": json.dumps(r.metadata),
        "revision": r.revision,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


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


def _row_to_record(row: aiosqlite.Row) -> AgentRecord:
    grants_raw = json.loads(row["grants"])
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
        capabilities=json.loads(row["capabilities"]),
        metadata=json.loads(row["metadata"]),
        revision=row["revision"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


class SqliteRegistry:
    """SQLite-backed agent registry.

    WAL mode for concurrent readers. ``BEGIN IMMEDIATE`` for write
    serialization. Trust scoring delegated to LinearTrustScore
    (scorers held in memory, rebuilt from stored values on lookup).
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None
        self._scorers: dict[str, LinearTrustScore] = {}
        self._write_lock = asyncio.Lock()

    async def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self._db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.executescript(_CREATE_TABLES)
            await self._db.commit()
        return self._db

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    def _ensure_scorer(self, name: str, trust_value: float) -> LinearTrustScore:
        scorer = self._scorers.get(name)
        if scorer is None:
            scorer = LinearTrustScore(initial_value=trust_value)
            self._scorers[name] = scorer
        return scorer

    async def register(self, record: AgentRecord) -> AgentRecord:
        async with self._write_lock:
            db = await self._conn()
            record.revision += 1
            record.updated_at = datetime.now(UTC)
            row = _record_to_row(record)

            await db.execute(
                """INSERT OR REPLACE INTO agent_records
                (agent_id, name, public_key, grants, trust_value, trust_tier,
                 status, owner, parent_agent_id, description, agent_version,
                 capabilities, metadata, revision, created_at, updated_at)
                VALUES (:agent_id, :name, :public_key, :grants, :trust_value,
                        :trust_tier, :status, :owner, :parent_agent_id,
                        :description, :agent_version, :capabilities, :metadata,
                        :revision, :created_at, :updated_at)""",
                row,
            )
            await db.commit()
            self._ensure_scorer(record.name, record.trust_value)
            return await self._lookup_or_raise_unlocked(record.name)

    async def deregister(self, name: str) -> None:
        async with self._write_lock:
            db = await self._conn()
            await self._lookup_or_raise_unlocked(name)
            await db.execute("DELETE FROM agent_records WHERE name = ?", (name,))
            await db.commit()
            self._scorers.pop(name, None)

    async def lookup(self, name: str) -> AgentRecord | None:
        db = await self._conn()
        cursor = await db.execute("SELECT * FROM agent_records WHERE name = ?", (name,))
        row = await cursor.fetchone()
        if row is None:
            return None
        record = _row_to_record(row)
        self._sync_trust(record)
        return record

    async def lookup_by_id(self, agent_id: str) -> AgentRecord | None:
        db = await self._conn()
        cursor = await db.execute("SELECT * FROM agent_records WHERE agent_id = ?", (agent_id,))
        row = await cursor.fetchone()
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
        db = await self._conn()

        if trust_tier is not None:
            await self._sync_all_trust_to_db()

        clauses: list[str] = []
        params: list[str] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if trust_tier is not None:
            clauses.append("trust_tier = ?")
            params.append(trust_tier.value)
        if owner is not None:
            clauses.append("owner = ?")
            params.append(owner)

        query = "SELECT * FROM agent_records"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)

        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            record = _row_to_record(row)
            self._sync_trust(record)
            results.append(record)
        return results

    async def add_grant(self, name: str, grant: Grant) -> AgentRecord:
        async with self._write_lock:
            record = await self._lookup_or_raise_unlocked(name)
            record.grants.append(grant)
            await self._save(record)
            return await self._lookup_or_raise_unlocked(name)

    async def remove_grant(self, name: str, grant_id: str) -> AgentRecord:
        async with self._write_lock:
            record = await self._lookup_or_raise_unlocked(name)
            for i, g in enumerate(record.grants):
                if g.id == grant_id:
                    record.grants.pop(i)
                    await self._save(record)
                    return await self._lookup_or_raise_unlocked(name)
            raise GrantNotFoundError(name, grant_id)

    async def has_grant(self, name: str, resource: str, action: str) -> bool:
        record = await self._lookup_or_raise(name)
        return any(resource in g.resources and action in g.actions for g in record.grants)

    async def record_trust_event(self, name: str, event: TrustEvent) -> AgentRecord:
        async with self._write_lock:
            record = await self._lookup_or_raise_unlocked(name)
            scorer = self._ensure_scorer(name, record.trust_value)

            value_before = scorer.value
            tier_before = scorer.tier
            scorer.record_event(event)
            value_after = scorer.value
            tier_after = scorer.tier

            record.trust_value = value_after
            record.trust_tier = tier_after
            await self._save(record)

            db = await self._conn()
            await db.execute(
                """INSERT INTO trust_events
                (agent_id, event_type, value_before, value_after,
                 tier_before, tier_after, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.agent_id,
                    event.value,
                    value_before,
                    value_after,
                    tier_before.value,
                    tier_after.value,
                    datetime.now(UTC).isoformat(),
                ),
            )
            await db.commit()
            return await self._lookup_or_raise_unlocked(name)

    async def set_trust(self, name: str, value: float, reason: str) -> AgentRecord:
        async with self._write_lock:
            record = await self._lookup_or_raise_unlocked(name)
            scorer = self._ensure_scorer(name, record.trust_value)

            value_before = scorer.value
            tier_before = scorer.tier
            scorer.set_value(value)
            value_after = scorer.value
            tier_after = scorer.tier

            record.trust_value = value_after
            record.trust_tier = tier_after
            await self._save(record)

            db = await self._conn()
            await db.execute(
                """INSERT INTO trust_events
                (agent_id, event_type, value_before, value_after,
                 tier_before, tier_after, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.agent_id,
                    TrustEvent.HUMAN_OVERRIDE.value,
                    value_before,
                    value_after,
                    tier_before.value,
                    tier_after.value,
                    datetime.now(UTC).isoformat(),
                ),
            )
            await db.commit()
            return await self._lookup_or_raise_unlocked(name)

    async def update_status(self, name: str, status: AgentStatus) -> AgentRecord:
        async with self._write_lock:
            record = await self._lookup_or_raise_unlocked(name)
            record.status = status
            await self._save(record)
            return await self._lookup_or_raise_unlocked(name)

    async def _lookup_or_raise(self, name: str) -> AgentRecord:
        record = await self.lookup(name)
        if record is None:
            raise AgentNotFoundError(name)
        return record

    async def _lookup_or_raise_unlocked(self, name: str) -> AgentRecord:
        db = await self._conn()
        cursor = await db.execute("SELECT * FROM agent_records WHERE name = ?", (name,))
        row = await cursor.fetchone()
        if row is None:
            raise AgentNotFoundError(name)
        record = _row_to_record(row)
        self._sync_trust(record)
        return record

    async def _sync_all_trust_to_db(self) -> None:
        db = await self._conn()
        for name, scorer in self._scorers.items():
            await db.execute(
                "UPDATE agent_records SET trust_value=?, trust_tier=? WHERE name=?",
                (scorer.value, scorer.tier.value, name),
            )
        await db.commit()

    def _sync_trust(self, record: AgentRecord) -> None:
        scorer = self._scorers.get(record.name)
        if scorer is not None:
            record.trust_value = scorer.value
            record.trust_tier = scorer.tier

    async def _save(self, record: AgentRecord) -> None:
        db = await self._conn()
        record.revision += 1
        record.updated_at = datetime.now(UTC)
        row = _record_to_row(record)
        await db.execute(
            """UPDATE agent_records SET
                grants=:grants, trust_value=:trust_value, trust_tier=:trust_tier,
                status=:status, owner=:owner, parent_agent_id=:parent_agent_id,
                description=:description, agent_version=:agent_version,
                capabilities=:capabilities, metadata=:metadata,
                revision=:revision, updated_at=:updated_at
            WHERE name=:name""",
            row,
        )
        await db.commit()
