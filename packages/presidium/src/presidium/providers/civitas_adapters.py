"""Real civitas.plugins.{model,tools} Protocol implementations.

Civitas is generic — it has no concept of governance. Presidium is the
opinionated layer that wraps a real backend (a real `ModelProvider`/
`ToolProvider`) with policy enforcement, producing something that still
*is* a real Civitas `ModelProvider`/`ToolProvider` — a drop-in replacement
for `self.llm`/an entry in `self.tools`, not a separate, parallel API.

**Real, load-bearing design constraint, not invented**: neither
`civitas.plugins.model.ModelProvider.chat()` nor
`civitas.plugins.tools.ToolProvider.execute()` carries agent identity in its
own call signature — `self.llm`/`self.tools` are typically shared across a
whole Supervisor tree (`agent.llm = self.llm` on spawn, per
`civitas/supervisor.py`). These adapters are therefore constructed **per
agent**, with `agent_name` bound at construction time — the exact,
already-established pattern `civitas.process.AgentProcess.connect_mcp()`
already uses for `civitas-io/fabrica`'s own `MCPTool`
(`MCPTool(client, schema, ..., agent_name=self.name)`), not a new one
invented here.

DENY (and a denied REQUIRE_APPROVAL) **raise** `PolicyDeniedError` — reusing
`GovernedModelProvider.check()`/`GovernedToolProvider.check()`'s existing,
unmodified behavior exactly. This is a real, deliberate difference from
`presidium_contrib.server`'s `check_grant()` path: an in-process Python
exception through the calling agent's own error boundary/supervision is the
correct, idiomatic Civitas convention here — there is no HTTP boundary to
keep from raising across.
"""

from __future__ import annotations

from typing import Any

from civitas.plugins.model import ModelProvider, ModelResponse
from civitas.plugins.tools import ToolProvider

from presidium.providers.model import GovernedModelProvider
from presidium.providers.tool import GovernedToolProvider


class GovernedModelProviderAdapter:
    """A real `civitas.plugins.model.ModelProvider` — checks, then delegates.

    Assign to a governed agent's own `self.llm` (or return from a
    `model_for`-style method) to make every `self.llm.chat(...)` call go
    through Presidium's policy engine first, transparently.
    """

    def __init__(
        self,
        *,
        backend: ModelProvider,
        model_provider: GovernedModelProvider,
        agent_name: str,
    ) -> None:
        self._backend = backend
        self._model_provider = model_provider
        self._agent_name = agent_name

    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[Any] | None = None,
    ) -> ModelResponse:
        """Check PRE_LLM policy, delegate to the real backend, check POST_LLM.

        Raises `PolicyDeniedError` on a PRE_LLM or POST_LLM deny — the real
        backend is never called at all on a PRE_LLM deny, and a POST_LLM
        deny propagates even though the real response was already obtained
        (post-execution validation exists precisely to catch and block bad
        output after seeing it).
        """
        await self._model_provider.check(self._agent_name, model)

        response = await self._backend.chat(model, messages, tools)

        result_data: dict[str, Any] = {
            "content": response.content,
            "model": response.model,
            "tokens_in": response.tokens_in,
            "tokens_out": response.tokens_out,
            "cost_usd": response.cost_usd,
        }
        await self._model_provider.post_check(self._agent_name, model, result_data)

        return response


class GovernedToolAdapter:
    """A real `civitas.plugins.tools.ToolProvider` — checks, then delegates.

    Wraps exactly one real underlying tool (`ToolProvider` represents a
    single named tool, unlike `GovernedToolProvider`'s own multi-tool
    check()/check_grant() interface) — register the returned adapter into a
    governed agent's own `self.tools` in place of the real tool directly.
    """

    def __init__(
        self,
        *,
        backend: ToolProvider,
        tool_provider: GovernedToolProvider,
        agent_name: str,
    ) -> None:
        self._backend = backend
        self._tool_provider = tool_provider
        self._agent_name = agent_name

    @property
    def name(self) -> str:
        return self._backend.name

    @property
    def schema(self) -> dict[str, Any]:
        return self._backend.schema

    async def execute(self, **kwargs: Any) -> Any:
        """Check PRE_TOOL policy, delegate to the real backend, check POST_TOOL.

        Raises `PolicyDeniedError` on a PRE_TOOL or POST_TOOL deny — the
        real tool is never invoked at all on a PRE_TOOL deny.
        """
        await self._tool_provider.check(self._agent_name, self.name)

        result = await self._backend.execute(**kwargs)

        # Real tool outputs are commonly already dict-shaped (JSON-like APIs);
        # a non-dict result (a string, a number, a list) is wrapped under a
        # single "value" key so post_check() always has a dict to evaluate,
        # matching EvaluationContext.result's own dict[str, Any] contract.
        result_data: dict[str, Any] = result if isinstance(result, dict) else {"value": result}
        await self._tool_provider.post_check(self._agent_name, self.name, "invoke", result_data)

        return result
