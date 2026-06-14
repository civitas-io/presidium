"""AgentGateway adapter — routes LLM calls through an AgentGateway instance."""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class AgentGatewayClient:
    """HTTP client for AgentGateway's OpenAI-compatible API.

    AgentGateway (Linux Foundation) provides unified LLM + MCP + A2A
    routing with native CEL policies and OpenTelemetry. This adapter
    wraps its ``/v1/chat/completions`` endpoint.

    Presidium handles authorization (grants, trust, approval routing)
    via GovernedModelProvider.check() BEFORE calling this client.
    AgentGateway handles operations (routing, rate limiting, cost).
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        *,
        api_key: str | None = None,
        default_model: str = "default",
        timeout: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._default_model = default_model
        self._timeout = timeout
        self._headers: dict[str, str] = headers or {}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"
        self._headers.setdefault("Content-Type", "application/json")

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        agent_name: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Send a chat completion request to AgentGateway.

        Returns the full OpenAI-compatible response dict.
        """
        body: dict[str, Any] = {
            "model": model or self._default_model,
            "messages": messages,
            **kwargs,
        }
        if agent_name:
            body.setdefault("metadata", {})["presidium_agent"] = agent_name

        url = f"{self._base_url}/v1/chat/completions"

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                json=body,
                headers=self._headers,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

    async def list_models(self) -> list[dict[str, Any]]:
        """List available models from AgentGateway."""
        url = f"{self._base_url}/v1/models"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url,
                headers=self._headers,
                timeout=self._timeout,
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            raw = data.get("data", [])
            result: list[dict[str, Any]] = list(raw) if isinstance(raw, list) else []
            return result

    async def health(self) -> bool:
        """Check if AgentGateway is reachable."""
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._base_url}/health",
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception:
            return False
