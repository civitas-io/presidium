from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from presidium.errors import PolicyDeniedError
from presidium.model import (
    AgentRecord,
    AgentStatus,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyRule,
    TrustTier,
)
from presidium.policy.cel import CelPolicyEngine
from presidium.registry.memory import InMemoryRegistry
from presidium.runtime import GovernedRuntime

ENFORCE_GRANTS = PolicyRule(
    name="enforce-grants",
    stage=[EvaluationStage.PRE_TOOL, EvaluationStage.PRE_LLM],
    expression="""
        !agent.grants.exists(g,
            request.resource in g.resources &&
            request.action in g.actions
        )
    """,
    decision=PolicyDecision.DENY,
    reason="No matching grant",
    priority=100,
)

TRUST_GATE_WRITES = PolicyRule(
    name="trust-gate-writes",
    stage=EvaluationStage.PRE_TOOL,
    expression='request.action == "write" && agent.trust.value < 0.7',
    decision=PolicyDecision.REQUIRE_APPROVAL,
    reason="Write actions require approval when trust < 0.7",
    approvers=("security@acme.com",),
    priority=90,
)


async def _make_runtime_with_agent(
    trust_value: float = 0.72,
    grants: list[Grant] | None = None,
) -> GovernedRuntime:
    engine = CelPolicyEngine()
    engine.load_policies([ENFORCE_GRANTS, TRUST_GATE_WRITES])

    registry = InMemoryRegistry()
    await registry.register(
        AgentRecord(
            agent_id="presidium://acme.com/prod/researcher",
            name="researcher",
            public_key="a2V5",
            trust_value=trust_value,
            trust_tier=TrustTier.TRUSTED if trust_value >= 0.7 else TrustTier.STANDARD,
            grants=grants
            if grants is not None
            else [
                Grant(resources=["tool:web_search"], actions=["invoke"], id="g1"),
                Grant(resources=["tool:database"], actions=["read"], id="g2"),
                Grant(resources=["llm:claude-sonnet"], actions=["invoke"], id="g3"),
            ],
            owner="alice@acme.com",
            status=AgentStatus.RUNNING,
        )
    )

    return GovernedRuntime(registry=registry, engine=engine)


class TestCompliantAgent:
    async def test_tool_call_with_matching_grant_succeeds(self) -> None:
        rt = await _make_runtime_with_agent()
        result = await rt.tool_provider.check("researcher", "web_search")
        assert result.decision == PolicyDecision.ALLOW

    async def test_llm_call_with_matching_grant_succeeds(self) -> None:
        rt = await _make_runtime_with_agent()
        result = await rt.model_provider.check("researcher", "claude-sonnet")
        assert result.decision == PolicyDecision.ALLOW

    async def test_read_action_succeeds(self) -> None:
        rt = await _make_runtime_with_agent()
        result = await rt.tool_provider.check("researcher", "database", "read")
        assert result.decision == PolicyDecision.ALLOW


class TestDeniedAgent:
    async def test_tool_call_without_grant_denied(self) -> None:
        rt = await _make_runtime_with_agent(grants=[])
        with pytest.raises(PolicyDeniedError) as exc_info:
            await rt.tool_provider.check("researcher", "web_search")
        assert exc_info.value.policy_name == "enforce-grants"

    async def test_llm_call_without_grant_denied(self) -> None:
        rt = await _make_runtime_with_agent(grants=[])
        with pytest.raises(PolicyDeniedError):
            await rt.model_provider.check("researcher", "claude-sonnet")

    async def test_wrong_action_denied(self) -> None:
        rt = await _make_runtime_with_agent(
            grants=[Grant(resources=["tool:database"], actions=["read"], id="g1")],
        )
        with pytest.raises(PolicyDeniedError):
            await rt.tool_provider.check("researcher", "database", "write")


class TestApprovalGated:
    async def test_low_trust_write_requires_approval(self) -> None:
        rt = await _make_runtime_with_agent(
            trust_value=0.5,
            grants=[Grant(resources=["tool:database"], actions=["write"], id="g1")],
        )
        from presidium.approval import CallbackApprovalProvider

        rt.approval = CallbackApprovalProvider(auto_approve=True)
        rt.tool_provider._approval = rt.approval
        result = await rt.tool_provider.check("researcher", "database", "write")
        assert result.decision == PolicyDecision.REQUIRE_APPROVAL

    async def test_high_trust_write_allowed(self) -> None:
        rt = await _make_runtime_with_agent(
            trust_value=0.8,
            grants=[Grant(resources=["tool:database"], actions=["write"], id="g1")],
        )
        result = await rt.tool_provider.check("researcher", "database", "write")
        assert result.decision == PolicyDecision.ALLOW


class TestFromConfig:
    async def test_from_config_loads_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "topology.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            supervision:
              name: root

            presidium:
              registry:
                trust_domain: acme.com
              policies:
                - name: deny-all
                  stage: pre_tool
                  expression: "true"
                  decision: deny
                  reason: "deny everything"
                  priority: 100
              agents:
                researcher:
                  owner: alice@acme.com
                  grants:
                    - resources: ["tool:web_search"]
                      actions: ["invoke"]
        """)
        )
        rt = GovernedRuntime.from_config(yaml_file)
        await rt.start()

        agent = await rt.registry.lookup("researcher")
        assert agent is not None
        assert agent.agent_id == "presidium://acme.com/researcher"
        assert agent.owner == "alice@acme.com"
        assert len(agent.grants) == 1

    async def test_from_config_policies_compiled(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "topology.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            supervision:
              name: root

            presidium:
              policies:
                - name: enforce-grants
                  stage: [pre_tool, pre_llm]
                  expression: >
                    !agent.grants.exists(g,
                      request.resource in g.resources &&
                      request.action in g.actions
                    )
                  decision: deny
                  reason: "No grant"
                  priority: 100
              agents:
                worker:
                  owner: bob@acme.com
        """)
        )
        rt = GovernedRuntime.from_config(yaml_file)
        await rt.start()

        with pytest.raises(PolicyDeniedError):
            await rt.tool_provider.check("worker", "database")

    async def test_from_config_no_presidium_block(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "topology.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            supervision:
              name: root
        """)
        )
        rt = GovernedRuntime.from_config(yaml_file)
        await rt.start()
        assert rt._trust_domain == "local"
