from __future__ import annotations

from unittest.mock import AsyncMock, patch

from presidium_contrib.agentgateway.client import AgentGatewayClient


def _mock_response(data: dict[str, object], status: int = 200) -> AsyncMock:
    mock_resp = AsyncMock()
    mock_resp.status_code = status
    mock_resp.raise_for_status = lambda: None
    mock_resp.json = lambda: data

    mock_client = AsyncMock()
    mock_client.post.return_value = mock_resp
    mock_client.get.return_value = mock_resp
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


CHAT_RESPONSE = {
    "id": "chatcmpl-123",
    "object": "chat.completion",
    "model": "claude-sonnet-4-20250514",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "Hello!"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
}


class TestAgentGatewayClientChat:
    async def test_sends_chat_request(self) -> None:
        mock_client = _mock_response(CHAT_RESPONSE)

        with patch(
            "presidium_contrib.agentgateway.client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            client = AgentGatewayClient("http://localhost:8080")
            result = await client.chat([{"role": "user", "content": "Hi"}], model="claude-sonnet")

        assert result["choices"][0]["message"]["content"] == "Hello!"
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "http://localhost:8080/v1/chat/completions"
        body = call_args[1]["json"]
        assert body["model"] == "claude-sonnet"
        assert body["messages"] == [{"role": "user", "content": "Hi"}]

    async def test_uses_default_model(self) -> None:
        mock_client = _mock_response(CHAT_RESPONSE)

        with patch(
            "presidium_contrib.agentgateway.client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            client = AgentGatewayClient(default_model="gpt-4o")
            await client.chat([{"role": "user", "content": "Hi"}])

        body = mock_client.post.call_args[1]["json"]
        assert body["model"] == "gpt-4o"

    async def test_includes_agent_name_in_metadata(self) -> None:
        mock_client = _mock_response(CHAT_RESPONSE)

        with patch(
            "presidium_contrib.agentgateway.client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            client = AgentGatewayClient()
            await client.chat([{"role": "user", "content": "Hi"}], agent_name="researcher")

        body = mock_client.post.call_args[1]["json"]
        assert body["metadata"]["presidium_agent"] == "researcher"

    async def test_api_key_sent_as_bearer(self) -> None:
        mock_client = _mock_response(CHAT_RESPONSE)

        with patch(
            "presidium_contrib.agentgateway.client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            client = AgentGatewayClient(api_key="sk-test-123")
            await client.chat([{"role": "user", "content": "Hi"}])

        headers = mock_client.post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer sk-test-123"

    async def test_passes_extra_kwargs(self) -> None:
        mock_client = _mock_response(CHAT_RESPONSE)

        with patch(
            "presidium_contrib.agentgateway.client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            client = AgentGatewayClient()
            await client.chat(
                [{"role": "user", "content": "Hi"}],
                temperature=0.7,
                max_tokens=100,
            )

        body = mock_client.post.call_args[1]["json"]
        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 100


class TestAgentGatewayClientListModels:
    async def test_lists_models(self) -> None:
        models_response = {
            "data": [
                {"id": "claude-sonnet", "object": "model"},
                {"id": "gpt-4o", "object": "model"},
            ]
        }
        mock_client = _mock_response(models_response)

        with patch(
            "presidium_contrib.agentgateway.client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            client = AgentGatewayClient()
            models = await client.list_models()

        assert len(models) == 2
        assert models[0]["id"] == "claude-sonnet"
        call_args = mock_client.get.call_args
        assert "/v1/models" in call_args[0][0]


class TestAgentGatewayClientHealth:
    async def test_healthy(self) -> None:
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "presidium_contrib.agentgateway.client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            client = AgentGatewayClient()
            assert await client.health() is True

    async def test_unhealthy(self) -> None:
        mock_client = AsyncMock()
        mock_client.get.side_effect = Exception("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "presidium_contrib.agentgateway.client.httpx.AsyncClient",
            return_value=mock_client,
        ):
            client = AgentGatewayClient()
            assert await client.health() is False
