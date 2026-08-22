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
                key_dir: {key_dir}
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
        """).format(key_dir=str(tmp_path / "keys"))
        )
        rt = GovernedRuntime.from_config(yaml_file)
        await rt.start()

        agent = await rt.registry.lookup("researcher")
        assert agent is not None
        assert agent.agent_id == "presidium://acme.com/researcher"
        assert agent.owner == "alice@acme.com"
        assert len(agent.grants) == 1
        assert agent.public_key != ""  # real Ed25519 identity binding, not the old hardcoded ""

    async def test_from_config_policies_compiled(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "topology.yaml"
        yaml_file.write_text(
            textwrap.dedent("""\
            supervision:
              name: root

            presidium:
              registry:
                key_dir: {key_dir}
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
        """).format(key_dir=str(tmp_path / "keys"))
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


class TestRealIdentityBinding:
    """2026-08-22 fix: GovernedRuntime.start() previously hardcoded
    public_key="" -- these prove it now binds a real, persistent Ed25519
    identity via civitas.security.identity.AgentIdentity.
    """

    async def test_start_binds_real_nonempty_public_key(self, tmp_path: Path) -> None:
        rt = GovernedRuntime(key_dir=tmp_path / "keys")
        rt._pending_agents = {"researcher": {"owner": "alice@acme.com"}}
        await rt.start()

        agent = await rt.registry.lookup("researcher")
        assert agent is not None
        assert agent.public_key != ""

        import base64

        assert len(base64.b64decode(agent.public_key)) == 32  # real Ed25519 verify key

    async def test_identity_persists_across_separate_runtime_instances(
        self, tmp_path: Path
    ) -> None:
        """Same key_dir, two separate GovernedRuntime instances -- same identity.

        Matches AgentRecord's own documented "persistent identity, survives
        restarts" contract (docs/rfcs/001-presidium-scope.md) -- a real restart
        must not silently rotate an agent's cryptographic identity.
        """
        key_dir = tmp_path / "keys"

        rt1 = GovernedRuntime(key_dir=key_dir)
        rt1._pending_agents = {"researcher": {}}
        await rt1.start()
        first_key = (await rt1.registry.lookup("researcher")).public_key  # type: ignore[union-attr]

        rt2 = GovernedRuntime(key_dir=key_dir)
        rt2._pending_agents = {"researcher": {}}
        await rt2.start()
        second_key = (await rt2.registry.lookup("researcher")).public_key  # type: ignore[union-attr]

        assert first_key == second_key

    async def test_different_agents_get_different_identities(self, tmp_path: Path) -> None:
        rt = GovernedRuntime(key_dir=tmp_path / "keys")
        rt._pending_agents = {"researcher": {}, "writer": {}}
        await rt.start()

        researcher = await rt.registry.lookup("researcher")
        writer = await rt.registry.lookup("writer")
        assert researcher is not None
        assert writer is not None
        assert researcher.public_key != writer.public_key

    async def test_registry_can_verify_a_real_signature_after_start(self, tmp_path: Path) -> None:
        """End-to-end: start() binds a real identity, the registry can verify
        a signature produced by that same agent's real private key."""
        from civitas.security.identity import AgentIdentity

        key_dir = tmp_path / "keys"
        rt = GovernedRuntime(key_dir=key_dir)
        rt._pending_agents = {"researcher": {}}
        await rt.start()

        # Load the same on-disk identity start() just created, to sign as
        # that agent would (e.g. for a future approval-decision attestation).
        identity = AgentIdentity.load("researcher", key_dir)
        data = b"approve production deploy"
        signature = identity.sign(data)

        assert await rt.registry.verify_signature("researcher", data, signature) is True
        assert (
            await rt.registry.verify_signature("researcher", b"different data", signature) is False
        )
