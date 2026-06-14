from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from presidium.model import Grant
from presidium_contrib.openbao.provider import OpenBaoCredentialProvider


@pytest.fixture()
def provider() -> OpenBaoCredentialProvider:
    with patch("presidium_contrib.openbao.provider.hvac.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        p = OpenBaoCredentialProvider(url="http://localhost:8200", token="test-token")
        p._client = mock_client
        return p


def _read_grant(name: str = "API_KEY") -> Grant:
    return Grant(resources=[f"credential:{name}"], actions=["read"])


class TestOpenBaoCredentialProvider:
    async def test_returns_value_with_grant(self, provider: OpenBaoCredentialProvider) -> None:
        provider._client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "sk-secret-123"}}
        }
        result = await provider.get("presidium://local/researcher", "API_KEY", [_read_grant()])
        assert result == "sk-secret-123"
        provider._client.secrets.kv.v2.read_secret_version.assert_called_once_with(
            path="agents/researcher/API_KEY",
            mount_point="secret",
        )

    async def test_returns_none_without_grant(self, provider: OpenBaoCredentialProvider) -> None:
        result = await provider.get("presidium://local/researcher", "API_KEY", [])
        assert result is None
        provider._client.secrets.kv.v2.read_secret_version.assert_not_called()

    async def test_returns_none_on_missing_secret(
        self, provider: OpenBaoCredentialProvider
    ) -> None:
        provider._client.secrets.kv.v2.read_secret_version.return_value = {"data": {"data": {}}}
        result = await provider.get("presidium://local/researcher", "API_KEY", [_read_grant()])
        assert result is None

    async def test_returns_none_on_vault_error(self, provider: OpenBaoCredentialProvider) -> None:
        provider._client.secrets.kv.v2.read_secret_version.side_effect = Exception(
            "connection refused"
        )
        result = await provider.get("presidium://local/researcher", "API_KEY", [_read_grant()])
        assert result is None

    async def test_extracts_agent_name_from_uri(self, provider: OpenBaoCredentialProvider) -> None:
        provider._client.secrets.kv.v2.read_secret_version.return_value = {
            "data": {"data": {"value": "val"}}
        }
        await provider.get(
            "presidium://acme.com/prod/orchestrator/child/w-3", "KEY", [_read_grant("KEY")]
        )
        call_args = provider._client.secrets.kv.v2.read_secret_version.call_args
        assert call_args[1]["path"] == "agents/w-3/KEY"

    async def test_custom_mount_point(self) -> None:
        with patch("presidium_contrib.openbao.provider.hvac.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            p = OpenBaoCredentialProvider(mount_point="kv")
            p._client = mock_client
            mock_client.secrets.kv.v2.read_secret_version.return_value = {
                "data": {"data": {"value": "x"}}
            }
            await p.get("presidium://local/t", "K", [_read_grant("K")])
            call_args = mock_client.secrets.kv.v2.read_secret_version.call_args
            assert call_args[1]["mount_point"] == "kv"

    async def test_close_is_noop(self, provider: OpenBaoCredentialProvider) -> None:
        await provider.close()
