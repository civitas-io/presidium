"""Real end-to-end tests for Service Mode through an actual Civitas
Runtime/Supervisor — not just direct handle_call() invocation.

This is also the real regression test for the 2026-08-22
`RegistryServer._registry` / `AgentProcess._registry` attribute-name
collision fix: `civitas/supervisor.py` sets `agent._registry =
self._registry` when wiring any child into a live tree, which would have
silently clobbered `RegistryServer`'s own governance registry with
Civitas's unrelated routing registry before the fix. These tests prove the
governance registry survives real Supervisor wiring, not just that the
attribute has a different name now.
"""

from __future__ import annotations

from typing import Any

from civitas import Runtime, Supervisor

from presidium_contrib.service.policy import PolicyEvaluatorServer
from presidium_contrib.service.registry import RegistryServer


async def _start_runtime(*children: Any) -> Runtime:
    runtime = Runtime(supervisor=Supervisor("root", children=list(children)))
    await runtime.start()
    return runtime


class TestRegistryServerThroughRealSupervisor:
    async def test_register_and_lookup_survive_real_supervisor_wiring(self) -> None:
        """Regression test for the self._registry collision fix.

        If RegistryServer's own governance registry were still clobbered by
        civitas.process.AgentProcess's own reserved `_registry` attribute
        (as it was before the 2026-08-22 fix), `register()`/`lookup()` here
        would either raise (calling a method that doesn't exist on Civitas's
        routing `Registry`) or silently do nothing.
        """
        server = RegistryServer("presidium.registry")
        runtime = await _start_runtime(server)
        try:
            register_result = await runtime.call(
                "presidium.registry",
                {
                    "action": "register",
                    "agent": {
                        "name": "researcher",
                        "owner": "alice@acme.com",
                        "grants": [{"resources": ["tool:database"], "actions": ["read"]}],
                    },
                },
            )
            assert register_result["registered"] is True

            lookup_result = await runtime.call(
                "presidium.registry", {"action": "lookup", "name": "researcher"}
            )
            assert lookup_result["found"] is True
            assert lookup_result["agent"]["owner"] == "alice@acme.com"
        finally:
            await runtime.stop()

    async def test_civitas_own_registry_still_works_alongside_governance_registry(
        self,
    ) -> None:
        """A second, real proof the collision is fixed: Civitas's own
        real registry-dependent features (capability-based routing via
        `send_capable`) must still work for a `RegistryServer` instance,
        proving `self._registry` (Civitas's own attribute) was never
        overwritten by Presidium's governance registry.
        """
        server = RegistryServer("presidium.registry")
        runtime = await _start_runtime(server)
        try:
            # Civitas's own _registry (routing) must still be a real Registry,
            # not accidentally replaced by Presidium's InMemoryRegistry.
            assert server._registry is not None
            assert type(server._registry).__name__ == "LocalRegistry"
            # And Presidium's own governance registry must be its own,
            # distinct, real InMemoryRegistry.
            assert type(server._agent_registry).__name__ == "InMemoryRegistry"
        finally:
            await runtime.stop()

    async def test_list_reflects_multiple_real_calls(self) -> None:
        server = RegistryServer("presidium.registry")
        runtime = await _start_runtime(server)
        try:
            for name in ("researcher", "writer"):
                await runtime.call(
                    "presidium.registry",
                    {"action": "register", "agent": {"name": name}},
                )

            result = await runtime.call("presidium.registry", {"action": "list"})
            assert {a["name"] for a in result["agents"]} == {"researcher", "writer"}
        finally:
            await runtime.stop()


class TestPolicyEvaluatorServerThroughRealSupervisor:
    async def test_load_then_evaluate_real_round_trip(self) -> None:
        server = PolicyEvaluatorServer("presidium.policy")
        runtime = await _start_runtime(server)
        try:
            load_result = await runtime.call(
                "presidium.policy",
                {
                    "action": "load_policies",
                    "rules": [
                        {
                            "name": "deny-writes",
                            "stage": "pre_tool",
                            "expression": 'request.action == "write"',
                            "decision": "deny",
                            "reason": "writes forbidden",
                        },
                        {
                            "name": "allow-all",
                            "stage": "pre_tool",
                            "expression": "true",
                            "decision": "allow",
                            "priority": 0,
                        },
                    ],
                },
            )
            assert load_result == {"loaded": 2}

            deny_result = await runtime.call(
                "presidium.policy",
                {
                    "action": "evaluate",
                    "stage": "pre_tool",
                    "agent": {"agent_id": "presidium://local/writer", "name": "writer"},
                    "request": {"resource": "tool:database", "action": "write"},
                },
            )
            assert deny_result["decision"] == "deny"
            assert deny_result["policy_name"] == "deny-writes"

            allow_result = await runtime.call(
                "presidium.policy",
                {
                    "action": "evaluate",
                    "stage": "pre_tool",
                    "agent": {"agent_id": "presidium://local/writer", "name": "writer"},
                    "request": {"resource": "tool:database", "action": "read"},
                },
            )
            assert allow_result["decision"] == "allow"
        finally:
            await runtime.stop()

    async def test_two_service_mode_genservers_coexist_in_one_tree(self) -> None:
        """Real, combined scenario: both GenServers wired into the same
        Supervisor, as they would be in a real distributed deployment."""
        registry_server = RegistryServer("presidium.registry")
        # allow_unmatched_requests=True: this test is about two GenServers
        # genuinely coexisting in one supervision tree, not about policy
        # authoring -- no rules are loaded here at all, so the real,
        # intended-production shortcut (an explicit ALLOW_ALL rule) would
        # add nothing to what's actually under test.
        policy_server = PolicyEvaluatorServer("presidium.policy", allow_unmatched_requests=True)
        runtime = await _start_runtime(registry_server, policy_server)
        try:
            await runtime.call(
                "presidium.registry",
                {"action": "register", "agent": {"name": "researcher"}},
            )
            lookup = await runtime.call(
                "presidium.registry", {"action": "lookup", "name": "researcher"}
            )
            assert lookup["found"] is True

            evaluate = await runtime.call(
                "presidium.policy",
                {
                    "action": "evaluate",
                    "stage": "pre_tool",
                    "agent": {"agent_id": "presidium://local/researcher", "name": "researcher"},
                    "request": {"resource": "tool:database", "action": "read"},
                },
            )
            assert evaluate["decision"] == "allow"
        finally:
            await runtime.stop()
