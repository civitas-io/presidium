from __future__ import annotations

import pytest

from presidium.model import AgentRecord, AgentStatus, Grant, TrustTier


@pytest.fixture()
def sample_grant() -> Grant:
    return Grant(
        resources=["tool:database"],
        actions=["read", "write"],
        scope={"environment": "prod"},
        condition="agent.trust.value >= 0.7",
        id="grant-001",
    )


@pytest.fixture()
def sample_agent(sample_grant: Grant) -> AgentRecord:
    return AgentRecord(
        agent_id="presidium://acme.com/prod/researcher",
        name="researcher",
        public_key="c29tZS1lZDI1NTE5LWtleQ==",
        grants=[sample_grant],
        trust_value=0.72,
        trust_tier=TrustTier.TRUSTED,
        status=AgentStatus.RUNNING,
        owner="alice@acme.com",
        description="Research agent",
        capabilities=["web_search", "database"],
    )
