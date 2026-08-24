"""Real tests for PolicyEvaluatorServer — previously 0% covered.

Exercises `handle_call()` directly. See
`tests/integration/test_service_mode_real_runtime.py` for the real
end-to-end test through an actual Civitas Runtime/Supervisor.
"""

from __future__ import annotations

from presidium_contrib.service.policy import PolicyEvaluatorServer


def _agent_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent_id": "presidium://local/researcher",
        "name": "researcher",
        "grants": [{"resources": ["tool:database"], "actions": ["read"]}],
    }
    payload.update(overrides)
    return payload


class TestHandleCallLoadPolicies:
    def test_load_policies_returns_count(self) -> None:
        server = PolicyEvaluatorServer()
        result = server._handle_load(
            {
                "rules": [
                    {
                        "name": "deny-all",
                        "stage": "pre_tool",
                        "expression": "true",
                        "decision": "deny",
                    }
                ]
            }
        )
        assert result == {"loaded": 1}

    def test_load_policies_empty_list(self) -> None:
        server = PolicyEvaluatorServer()
        result = server._handle_load({"rules": []})
        assert result == {"loaded": 0}

    def test_load_policies_multi_stage_rule(self) -> None:
        server = PolicyEvaluatorServer()
        result = server._handle_load(
            {
                "rules": [
                    {
                        "name": "multi",
                        "stage": ["pre_tool", "pre_llm"],
                        "expression": "true",
                        "decision": "deny",
                    }
                ]
            }
        )
        assert result == {"loaded": 1}


class TestHandleCallEvaluate:
    async def test_evaluate_denies_when_no_rules_loaded_real_default_2026_08_24(self) -> None:
        """Real, current default -- flipped from allow, see
        docs/design/policy-engine.md's "Design Decisions" P5."""
        server = PolicyEvaluatorServer()
        result = await server.handle_call(
            {
                "action": "evaluate",
                "stage": "pre_tool",
                "agent": _agent_payload(),
                "request": {"resource": "tool:database", "action": "read"},
            },
            "sender",
        )
        assert result["decision"] == "deny"
        assert result["policy_name"] is None

    async def test_evaluate_allow_unmatched_requests_true_restores_old_behavior(self) -> None:
        server = PolicyEvaluatorServer(allow_unmatched_requests=True)
        result = await server.handle_call(
            {
                "action": "evaluate",
                "stage": "pre_tool",
                "agent": _agent_payload(),
                "request": {"resource": "tool:database", "action": "read"},
            },
            "sender",
        )
        assert result["decision"] == "allow"
        assert result["policy_name"] is None

    async def test_evaluate_deny_via_loaded_rule(self) -> None:
        server = PolicyEvaluatorServer()
        server._handle_load(
            {
                "rules": [
                    {
                        "name": "deny-writes",
                        "stage": "pre_tool",
                        "expression": 'request.action == "write"',
                        "decision": "deny",
                        "reason": "writes forbidden",
                    }
                ]
            }
        )

        result = await server.handle_call(
            {
                "action": "evaluate",
                "stage": "pre_tool",
                "agent": _agent_payload(),
                "request": {"resource": "tool:database", "action": "write"},
            },
            "sender",
        )
        assert result["decision"] == "deny"
        assert result["policy_name"] == "deny-writes"
        assert result["reason"] == "writes forbidden"

    async def test_evaluate_uses_real_grant_data(self) -> None:
        server = PolicyEvaluatorServer()
        server._handle_load(
            {
                "rules": [
                    {
                        "name": "require-grant",
                        "stage": "pre_tool",
                        "expression": (
                            "!agent.grants.exists(g, "
                            "request.resource in g.resources && "
                            "request.action in g.actions)"
                        ),
                        "decision": "deny",
                        "reason": "no matching grant",
                    },
                    {
                        "name": "allow-all",
                        "stage": "pre_tool",
                        "expression": "true",
                        "decision": "allow",
                        "priority": 0,
                    },
                ]
            }
        )

        denied = await server.handle_call(
            {
                "action": "evaluate",
                "stage": "pre_tool",
                "agent": _agent_payload(grants=[]),
                "request": {"resource": "tool:database", "action": "read"},
            },
            "sender",
        )
        assert denied["decision"] == "deny"

        allowed = await server.handle_call(
            {
                "action": "evaluate",
                "stage": "pre_tool",
                "agent": _agent_payload(),
                "request": {"resource": "tool:database", "action": "read"},
            },
            "sender",
        )
        assert allowed["decision"] == "allow"

    async def test_evaluate_post_stage_with_result_payload(self) -> None:
        server = PolicyEvaluatorServer()
        server._handle_load(
            {
                "rules": [
                    {
                        "name": "block-large-results",
                        "stage": "post_tool",
                        "expression": "result.size > 1000",
                        "decision": "deny",
                    }
                ]
            }
        )

        result = await server.handle_call(
            {
                "action": "evaluate",
                "stage": "post_tool",
                "agent": _agent_payload(),
                "request": {"resource": "tool:database", "action": "read"},
                "result": {"size": 2000},
            },
            "sender",
        )
        assert result["decision"] == "deny"
        assert result["policy_name"] == "block-large-results"


class TestHandleCallUnknownAction:
    async def test_unknown_action_returns_error(self) -> None:
        server = PolicyEvaluatorServer()
        result = await server.handle_call({"action": "nonexistent"}, "sender")
        assert "error" in result
        assert "nonexistent" in result["error"]

    async def test_missing_action_returns_error(self) -> None:
        server = PolicyEvaluatorServer()
        result = await server.handle_call({}, "sender")
        assert "error" in result
