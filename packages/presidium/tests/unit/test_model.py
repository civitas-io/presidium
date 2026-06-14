from __future__ import annotations

import copy
import json
from dataclasses import asdict
from datetime import UTC, datetime

import pytest

from presidium.model import (
    ActionRequest,
    AgentRecord,
    AgentStatus,
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    EnforcementMode,
    EvaluationContext,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyResult,
    PolicyRule,
    TrustEvent,
    TrustTier,
)


class TestAgentStatusEnum:
    def test_all_values(self) -> None:
        expected = {"registered", "starting", "running", "stopping", "stopped", "suspended"}
        assert {s.value for s in AgentStatus} == expected

    def test_exhaustive_count(self) -> None:
        assert len(AgentStatus) == 6


class TestTrustTierEnum:
    def test_all_values(self) -> None:
        expected = {"trusted", "standard", "restricted"}
        assert {t.value for t in TrustTier} == expected

    def test_exhaustive_count(self) -> None:
        assert len(TrustTier) == 3


class TestTrustEventEnum:
    def test_all_values(self) -> None:
        expected = {"success", "failure", "policy_violation", "human_override"}
        assert {e.value for e in TrustEvent} == expected

    def test_exhaustive_count(self) -> None:
        assert len(TrustEvent) == 4


class TestPolicyDecisionEnum:
    def test_all_values(self) -> None:
        expected = {"allow", "deny", "require_approval"}
        assert {d.value for d in PolicyDecision} == expected

    def test_exhaustive_count(self) -> None:
        assert len(PolicyDecision) == 3


class TestEvaluationStageEnum:
    def test_all_values(self) -> None:
        expected = {"pre_tool", "pre_llm", "registration", "post_tool", "post_llm"}
        assert {s.value for s in EvaluationStage} == expected

    def test_exhaustive_count(self) -> None:
        assert len(EvaluationStage) == 5


class TestEnforcementModeEnum:
    def test_all_values(self) -> None:
        expected = {"advisory", "soft", "hard"}
        assert {m.value for m in EnforcementMode} == expected

    def test_exhaustive_count(self) -> None:
        assert len(EnforcementMode) == 3


class TestApprovalStatusEnum:
    def test_all_values(self) -> None:
        expected = {"pending", "approved", "denied", "timed_out"}
        assert {s.value for s in ApprovalStatus} == expected

    def test_exhaustive_count(self) -> None:
        assert len(ApprovalStatus) == 4


class TestGrant:
    def test_construction_minimal(self) -> None:
        g = Grant(resources=["tool:db"], actions=["read"])
        assert g.resources == ["tool:db"]
        assert g.actions == ["read"]
        assert g.scope == {}
        assert g.condition is None
        assert g.expires_at is None
        assert g.id

    def test_construction_full(self) -> None:
        exp = datetime(2026, 12, 31, tzinfo=UTC)
        g = Grant(
            resources=["tool:database", "llm:claude-sonnet"],
            actions=["read", "write"],
            scope={"environment": "prod", "tenant": "acme"},
            condition="agent.trust.value >= 0.7",
            expires_at=exp,
            id="my-grant",
        )
        assert g.resources == ["tool:database", "llm:claude-sonnet"]
        assert g.scope["tenant"] == "acme"
        assert g.condition == "agent.trust.value >= 0.7"
        assert g.expires_at == exp
        assert g.id == "my-grant"

    def test_auto_generated_ids_are_unique(self) -> None:
        g1 = Grant(resources=["a"], actions=["b"])
        g2 = Grant(resources=["a"], actions=["b"])
        assert g1.id != g2.id

    def test_condition_accepts_cel_strings(self) -> None:
        cel_expr = 'agent.grants.exists(g, "tool:db" in g.resources && "read" in g.actions)'
        g = Grant(resources=["tool:db"], actions=["read"], condition=cel_expr)
        assert g.condition == cel_expr

    def test_json_round_trip(self) -> None:
        g = Grant(resources=["tool:db"], actions=["read"], id="stable-id")
        d = asdict(g)
        serialized = json.dumps(d, default=str)
        deserialized = json.loads(serialized)
        assert deserialized["resources"] == ["tool:db"]
        assert deserialized["id"] == "stable-id"


class TestAgentRecord:
    def test_construction_minimal(self) -> None:
        r = AgentRecord(
            agent_id="presidium://local/test",
            name="test",
            public_key="dGVzdC1rZXk=",
        )
        assert r.agent_id == "presidium://local/test"
        assert r.name == "test"
        assert r.trust_value == 0.5
        assert r.trust_tier == TrustTier.STANDARD
        assert r.status == AgentStatus.REGISTERED
        assert r.grants == []
        assert r.revision == 0
        assert r.owner is None
        assert r.parent_agent_id is None

    def test_agent_id_accepts_presidium_uri(self) -> None:
        r = AgentRecord(
            agent_id="presidium://acme.com/prod/researcher",
            name="researcher",
            public_key="a2V5",
        )
        assert r.agent_id.startswith("presidium://")

    def test_agent_id_accepts_nested_paths(self) -> None:
        r = AgentRecord(
            agent_id="presidium://acme.com/prod/orchestrator/child/w-3",
            name="worker-3",
            public_key="a2V5",
        )
        assert "orchestrator/child/w-3" in r.agent_id

    def test_timestamps_are_utc(self) -> None:
        r = AgentRecord(
            agent_id="presidium://local/t",
            name="t",
            public_key="a2V5",
        )
        assert r.created_at.tzinfo is not None
        assert r.updated_at.tzinfo is not None
        assert r.created_at.tzinfo == UTC

    def test_defaults(self) -> None:
        r = AgentRecord(
            agent_id="presidium://local/t",
            name="t",
            public_key="a2V5",
        )
        assert r.capabilities == []
        assert r.metadata == {}
        assert r.description is None
        assert r.agent_version is None

    def test_json_round_trip(self) -> None:
        r = AgentRecord(
            agent_id="presidium://local/t",
            name="t",
            public_key="a2V5",
            grants=[Grant(resources=["tool:db"], actions=["read"], id="g1")],
            owner="bob@acme.com",
        )
        d = asdict(r)
        serialized = json.dumps(d, default=str)
        deserialized = json.loads(serialized)
        assert deserialized["agent_id"] == "presidium://local/t"
        assert deserialized["owner"] == "bob@acme.com"
        assert len(deserialized["grants"]) == 1
        assert deserialized["grants"][0]["id"] == "g1"

    def test_equality(self) -> None:
        now = datetime.now(UTC)
        kwargs = dict(
            agent_id="presidium://local/t",
            name="t",
            public_key="a2V5",
            created_at=now,
            updated_at=now,
        )
        r1 = AgentRecord(**kwargs)  # type: ignore[arg-type]
        r2 = AgentRecord(**kwargs)  # type: ignore[arg-type]
        assert r1 == r2

    def test_mutation(self) -> None:
        r = AgentRecord(
            agent_id="presidium://local/t",
            name="t",
            public_key="a2V5",
        )
        r.trust_value = 0.8
        r.trust_tier = TrustTier.TRUSTED
        r.revision += 1
        assert r.trust_value == 0.8
        assert r.trust_tier == TrustTier.TRUSTED
        assert r.revision == 1

    def test_copy_produces_independent_snapshot(self) -> None:
        r = AgentRecord(
            agent_id="presidium://local/t",
            name="t",
            public_key="a2V5",
            grants=[Grant(resources=["tool:db"], actions=["read"], id="g1")],
        )
        snapshot = copy.deepcopy(r)
        r.grants.append(Grant(resources=["llm:x"], actions=["invoke"], id="g2"))
        assert len(snapshot.grants) == 1
        assert len(r.grants) == 2


class TestPolicyRule:
    def test_construction(self) -> None:
        rule = PolicyRule(
            name="enforce-grants",
            stage=EvaluationStage.PRE_TOOL,
            expression="agent.grants.exists(g, request.resource in g.resources)",
            decision=PolicyDecision.DENY,
            reason="No matching grant",
            priority=100,
        )
        assert rule.name == "enforce-grants"
        assert rule.stage == EvaluationStage.PRE_TOOL
        assert rule.enforcement == EnforcementMode.HARD
        assert rule.enabled is True
        assert rule.approvers == ()

    def test_frozen(self) -> None:
        rule = PolicyRule(
            name="test",
            stage=EvaluationStage.PRE_TOOL,
            expression="true",
            decision=PolicyDecision.ALLOW,
        )
        with pytest.raises(AttributeError):
            rule.name = "modified"  # type: ignore[misc]

    def test_multi_stage(self) -> None:
        rule = PolicyRule(
            name="multi",
            stage=[EvaluationStage.PRE_TOOL, EvaluationStage.PRE_LLM],
            expression="true",
            decision=PolicyDecision.DENY,
        )
        assert isinstance(rule.stage, list)
        assert len(rule.stage) == 2

    def test_approvers_as_tuple(self) -> None:
        rule = PolicyRule(
            name="approval",
            stage=EvaluationStage.PRE_TOOL,
            expression="true",
            decision=PolicyDecision.REQUIRE_APPROVAL,
            approvers=("admin@acme.com", "security@acme.com"),
        )
        assert len(rule.approvers) == 2


class TestPolicyResult:
    def test_allow_result(self) -> None:
        r = PolicyResult(
            decision=PolicyDecision.ALLOW,
            policy_name=None,
            reason="All policies passed",
        )
        assert r.decision == PolicyDecision.ALLOW
        assert r.policy_name is None

    def test_deny_result(self) -> None:
        r = PolicyResult(
            decision=PolicyDecision.DENY,
            policy_name="enforce-grants",
            reason="No matching grant",
            enforcement=EnforcementMode.HARD,
        )
        assert r.decision == PolicyDecision.DENY
        assert r.policy_name == "enforce-grants"


class TestActionRequest:
    def test_construction(self) -> None:
        req = ActionRequest(resource="tool:database", action="read")
        assert req.resource == "tool:database"
        assert req.action == "read"
        assert req.parameters == {}

    def test_with_parameters(self) -> None:
        req = ActionRequest(
            resource="llm:claude-sonnet",
            action="invoke",
            parameters={"max_tokens": 1000},
        )
        assert req.parameters["max_tokens"] == 1000


class TestEvaluationContext:
    def test_construction(self, sample_agent: AgentRecord) -> None:
        ctx = EvaluationContext(
            agent=sample_agent,
            request=ActionRequest(resource="tool:db", action="read"),
            time=datetime.now(UTC),
        )
        assert ctx.agent.name == "researcher"
        assert ctx.request.resource == "tool:db"


class TestApprovalRequest:
    def test_construction(self) -> None:
        req = ApprovalRequest(
            request_id="req-001",
            agent_id="presidium://acme.com/prod/researcher",
            resource="tool:database",
            action="write",
            reason="Low trust for write",
            approvers=["security@acme.com"],
            context={"trust_value": 0.5},
            policy_name="trust-gate-writes",
        )
        assert req.status == ApprovalStatus.PENDING
        assert req.timeout_seconds == 300.0

    def test_custom_timeout(self) -> None:
        req = ApprovalRequest(
            request_id="req-002",
            agent_id="presidium://local/t",
            resource="tool:db",
            action="write",
            reason="test",
            approvers=[],
            context={},
            policy_name="test",
            timeout_seconds=60.0,
        )
        assert req.timeout_seconds == 60.0


class TestApprovalDecision:
    def test_approved(self) -> None:
        d = ApprovalDecision(
            request_id="req-001",
            approved=True,
            decided_by="admin@acme.com",
            reason="Looks good",
        )
        assert d.approved is True

    def test_denied(self) -> None:
        d = ApprovalDecision(
            request_id="req-001",
            approved=False,
            decided_by="admin@acme.com",
        )
        assert d.approved is False
        assert d.reason is None


class TestPublicImports:
    def test_import_from_presidium(self) -> None:
        from presidium import (
            AgentStatus,
            PolicyDecision,
            TrustTier,
        )

        assert AgentStatus.RUNNING.value == "running"
        assert TrustTier.TRUSTED.value == "trusted"
        assert PolicyDecision.DENY.value == "deny"

    def test_import_errors(self) -> None:
        from presidium import (
            PolicyDeniedError,
            PolicyEvaluationError,
            PresidiumError,
        )

        assert issubclass(PolicyDeniedError, PresidiumError)
        assert issubclass(PolicyEvaluationError, PresidiumError)


class TestErrors:
    def test_policy_denied_error(self) -> None:
        from presidium.errors import PolicyDeniedError

        e = PolicyDeniedError("No grant", "enforce-grants")
        assert "enforce-grants" in str(e)
        assert e.policy_name == "enforce-grants"
        assert e.reason == "No grant"

    def test_policy_evaluation_error(self) -> None:
        from presidium.errors import PolicyEvaluationError

        e = PolicyEvaluationError("test-policy", "division by zero")
        assert e.policy_name == "test-policy"
        assert "division by zero" in str(e)

    def test_policy_compilation_error(self) -> None:
        from presidium.errors import PolicyCompilationError

        e = PolicyCompilationError("bad-rule", "invalid(", "syntax error")
        assert e.policy_name == "bad-rule"
        assert e.expression == "invalid("
        assert "syntax error" in str(e)

    def test_agent_not_found_error(self) -> None:
        from presidium.errors import AgentNotFoundError

        e = AgentNotFoundError("missing-agent")
        assert e.agent_name == "missing-agent"
        assert "missing-agent" in str(e)

    def test_grant_not_found_error(self) -> None:
        from presidium.errors import GrantNotFoundError

        e = GrantNotFoundError("researcher", "grant-999")
        assert e.agent_name == "researcher"
        assert e.grant_id == "grant-999"

    def test_credential_access_denied(self) -> None:
        from presidium.errors import CredentialAccessDenied

        e = CredentialAccessDenied("presidium://local/t", "API_KEY")
        assert e.agent_id == "presidium://local/t"
        assert e.credential_name == "API_KEY"

    def test_approval_timeout_error(self) -> None:
        from presidium.errors import ApprovalTimeoutError

        e = ApprovalTimeoutError("req-001", 300.0)
        assert e.request_id == "req-001"
        assert e.timeout_seconds == 300.0

    def test_error_hierarchy(self) -> None:
        from presidium.errors import (
            AgentNotFoundError,
            PresidiumError,
            RegistryError,
        )

        assert issubclass(RegistryError, PresidiumError)
        assert issubclass(AgentNotFoundError, RegistryError)

    def test_all_errors_are_presidium_errors(self) -> None:
        from presidium.errors import (
            AgentNotFoundError,
            ApprovalTimeoutError,
            CredentialAccessDenied,
            GrantNotFoundError,
            PolicyCompilationError,
            PolicyDeniedError,
            PolicyEvaluationError,
            PresidiumError,
            RegistryError,
        )

        for cls in [
            PolicyEvaluationError,
            PolicyCompilationError,
            PolicyDeniedError,
            RegistryError,
            AgentNotFoundError,
            GrantNotFoundError,
            CredentialAccessDenied,
            ApprovalTimeoutError,
        ]:
            assert issubclass(cls, PresidiumError), f"{cls.__name__} is not a PresidiumError"
