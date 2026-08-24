"""GovernedMcpToolPipeline -- composes the three real, previously-independent MCP governance
primitives (PoisoningDetector, PIIDetector, credential redaction) with authorization
(GovernedToolProvider) and a real ToolsGatewayBackend into one invokable pipeline.

Before this module, all three primitives were real, tested, shipped code
(presidium_contrib.mcp_gateway.{poisoning,pii,redaction}) with zero real composition -- nothing
in this codebase ever called them together, or called them from the actual tool-call path at
all. docs/design/mcp-gateway.md's own "Tool Poisoning Detection"/"Credential Redaction"/"Output
PII Masking" sections describe exactly this shape (poisoning check before calling, redact
parameters before audit, PII-scan-then-enrich the result before POST_TOOL policy evaluation) --
this class is the real implementation of that description, not a new design.

Deliberately NOT built as an extension of GatewayToolProvider (presidium/providers/gateway.py):
that class calls the backend then immediately runs post_check() on the raw result -- there is no
seam to inject PII-scan enrichment between "get the result" and "evaluate POST_TOOL policy
against it" without either reaching into GatewayToolProvider's internals or duplicating its
control flow. This class orchestrates GovernedToolProvider (pure authorization) and a
ToolsGatewayBackend directly instead -- the same two primitives GatewayToolProvider composes,
just with the extra enrichment steps spliced in between them. GatewayToolProvider remains the
right choice for callers who don't need MCP governance primitives; this is a specialized,
heavier-weight alternative for callers who do, not a replacement.
"""

from __future__ import annotations

from typing import Any

from presidium.errors import PresidiumError
from presidium.providers.gateway import ToolsGatewayBackend
from presidium.providers.tool import GovernedToolProvider
from presidium_contrib.mcp_gateway.pii import PIIDetector
from presidium_contrib.mcp_gateway.poisoning import PoisoningDetector, PoisoningStatus
from presidium_contrib.mcp_gateway.redaction import redact_dict


class ToolPoisoningDetectedError(PresidiumError):
    """Raised when a tool call is blocked because the tool is unapproved or has changed since
    approval -- fail-closed by default (see GovernedMcpToolPipeline's own
    allow_unapproved_tools), matching this org's allow_unmatched_requests/allow_ungoverned/
    allow_unsandboxed naming and fail-closed-by-default convention.
    """

    def __init__(self, tool_name: str, status: PoisoningStatus, detail: str | None) -> None:
        self.tool_name = tool_name
        self.status = status
        self.detail = detail
        reason = detail or status.value
        super().__init__(f"Tool {tool_name!r} failed poisoning check ({status.value}): {reason}")


class GovernedMcpToolPipeline:
    """One real, invokable pipeline: poisoning check -> redact-for-audit -> PRE_TOOL
    authorization -> real tool call -> PII scan/enrich -> POST_TOOL authorization -> optional
    PII masking of the value actually returned to the agent.

    Bound to one agent_name at construction, matching GatewayToolProvider/GatewayModelProvider's
    own established per-agent-construction precedent.
    """

    def __init__(
        self,
        *,
        backend: ToolsGatewayBackend,
        tool_provider: GovernedToolProvider,
        agent_name: str,
        poisoning_detector: PoisoningDetector | None = None,
        pii_detector: PIIDetector | None = None,
        allow_unapproved_tools: bool = False,
        mask_pii_in_results: bool = True,
    ) -> None:
        self._backend = backend
        self._tool_provider = tool_provider
        self._agent_name = agent_name
        self._poisoning_detector = poisoning_detector or PoisoningDetector()
        # None is a real, deliberate opt-out -- PII scanning is not free (scans every string in
        # every result), and not every deployment wants it. Matches PoisoningDetector always
        # being present (poisoning checks are cheap, hash comparisons only) vs. PII scanning
        # being explicitly opt-in-by-presence.
        self._pii_detector = pii_detector
        self._allow_unapproved_tools = allow_unapproved_tools
        self._mask_pii_in_results = mask_pii_in_results

    async def list_tools(self) -> list[dict[str, Any]]:
        """No PRE_TOOL check -- discovery, not invocation, matching GatewayToolProvider's own
        list_tools() exemption (mcp-gateway.md decision 4). Real, additive enrichment beyond
        GatewayToolProvider's own list_tools(): each returned tool dict gains a
        "poisoning_status" key so a caller (or an admin UI) can see which tools are
        unapproved/changed without a separate round trip.
        """
        tools = await self._backend.list_tools(agent_name=self._agent_name)
        enriched: list[dict[str, Any]] = []
        for tool in tools:
            result = self._poisoning_detector.check(
                tool["name"], tool.get("description", ""), tool.get("input_schema", {})
            )
            enriched.append({**tool, "poisoning_status": result.status.value})
        return enriched

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        tool_description: str | None = None,
        tool_input_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Real, full pipeline for one tool call.

        ``tool_description``/``tool_input_schema`` are optional -- if the caller already knows
        them (e.g. from a prior list_tools() call), passing them here avoids a second, real
        network round trip to re-list tools just to run the poisoning check. If omitted, this
        method fetches the live definition via list_tools() itself -- a real, honest cost,
        not hidden.

        Raises ToolPoisoningDetectedError (fail-closed by default) if the tool is unapproved or
        has changed since approval. Raises PolicyDeniedError on a PRE_TOOL or POST_TOOL deny --
        the backend is never called at all on a PRE_TOOL deny, matching GatewayToolProvider's own
        convention exactly.
        """
        if tool_description is None or tool_input_schema is None:
            live_tools = await self._backend.list_tools(agent_name=self._agent_name)
            match = next((t for t in live_tools if t["name"] == name), None)
            tool_description = match.get("description", "") if match else ""
            tool_input_schema = match.get("input_schema", {}) if match else {}

        poisoning_result = self._poisoning_detector.check(name, tool_description, tool_input_schema)
        if poisoning_result.status != PoisoningStatus.CLEAN and not self._allow_unapproved_tools:
            raise ToolPoisoningDetectedError(name, poisoning_result.status, poisoning_result.detail)

        # Real parameters flow into ActionRequest.parameters (per FR-1.4's own general
        # mechanism, threaded through check()/check_resource()/check_grant() earlier this
        # session) -- redacted before that happens, so neither a CEL policy author nor an audit
        # log ever sees a raw credential that happened to be passed as a tool argument.
        redacted_arguments = redact_dict(arguments)
        await self._tool_provider.check(self._agent_name, name, parameters=redacted_arguments)

        result = await self._backend.call_tool(name, arguments, agent_name=self._agent_name)

        if self._pii_detector is not None:
            pii_result = self._pii_detector.scan_dict(result)
            result = {
                **result,
                "contains_pii": pii_result.contains_pii,
                "pii_pattern_names": pii_result.pattern_names,
            }

        await self._tool_provider.post_check(self._agent_name, name, "invoke", result)

        if (
            self._pii_detector is not None
            and result.get("contains_pii")
            and self._mask_pii_in_results
        ):
            masked = self._pii_detector.mask_dict(result)
            # mask_dict() only touches string values -- contains_pii/pii_pattern_names are a
            # bool and a list, both passed through unchanged, so re-asserting them here is
            # redundant, not a correction -- kept explicit anyway so this fact doesn't need to
            # be re-derived by reading mask_dict()'s own implementation.
            masked["contains_pii"] = True
            masked["pii_pattern_names"] = result["pii_pattern_names"]
            result = masked

        return result

    async def health(self) -> bool:
        return await self._backend.health()

    def approve_tool(
        self, name: str, description: str, parameters: dict[str, Any], approved_by: str
    ) -> None:
        """Convenience passthrough to the underlying PoisoningDetector -- lets a caller approve
        a tool through the pipeline object directly, without needing to keep a separate
        PoisoningDetector reference alive just for this one call.
        """
        self._poisoning_detector.approve_tool(name, description, parameters, approved_by)
