from __future__ import annotations

from pathlib import Path

import pytest

from presidium.credentials import (
    CredentialProvider,
    EnvCredentialProvider,
    FileCredentialProvider,
    _has_credential_grant,
)
from presidium.model import Grant


class TestHasCredentialGrant:
    def test_matching_grant(self) -> None:
        grants = [Grant(resources=["credential:API_KEY"], actions=["read"])]
        assert _has_credential_grant(grants, "API_KEY") is True

    def test_no_matching_resource(self) -> None:
        grants = [Grant(resources=["tool:database"], actions=["read"])]
        assert _has_credential_grant(grants, "API_KEY") is False

    def test_no_read_action(self) -> None:
        grants = [Grant(resources=["credential:API_KEY"], actions=["write"])]
        assert _has_credential_grant(grants, "API_KEY") is False

    def test_empty_grants(self) -> None:
        assert _has_credential_grant([], "API_KEY") is False

    def test_multiple_grants_one_matches(self) -> None:
        grants = [
            Grant(resources=["tool:db"], actions=["read"]),
            Grant(resources=["credential:API_KEY"], actions=["read", "write"]),
        ]
        assert _has_credential_grant(grants, "API_KEY") is True


class TestEnvCredentialProviderProtocol:
    def test_satisfies_protocol(self) -> None:
        provider = EnvCredentialProvider()
        assert isinstance(provider, CredentialProvider)


class TestEnvCredentialProvider:
    @pytest.fixture()
    def provider(self) -> EnvCredentialProvider:
        return EnvCredentialProvider()

    @pytest.fixture()
    def read_grant(self) -> Grant:
        return Grant(resources=["credential:TEST_SECRET"], actions=["read"])

    async def test_returns_value_with_grant(
        self, provider: EnvCredentialProvider, read_grant: Grant, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_SECRET", "secret-value")
        result = await provider.get("presidium://local/t", "TEST_SECRET", [read_grant])
        assert result == "secret-value"

    async def test_returns_none_without_grant(
        self, provider: EnvCredentialProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TEST_SECRET", "secret-value")
        result = await provider.get("presidium://local/t", "TEST_SECRET", [])
        assert result is None

    async def test_returns_none_when_not_in_env(
        self, provider: EnvCredentialProvider, read_grant: Grant, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("TEST_SECRET", raising=False)
        monkeypatch.delenv("test_secret", raising=False)
        result = await provider.get("presidium://local/t", "TEST_SECRET", [read_grant])
        assert result is None

    async def test_case_insensitive_lookup(
        self, provider: EnvCredentialProvider, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        grant = Grant(resources=["credential:api_key"], actions=["read"])
        monkeypatch.setenv("API_KEY", "found-upper")
        result = await provider.get("presidium://local/t", "api_key", [grant])
        assert result == "found-upper"

    async def test_close_is_noop(self, provider: EnvCredentialProvider) -> None:
        await provider.close()


class TestFileCredentialProvider:
    @pytest.fixture()
    def secrets_file(self, tmp_path: Path) -> Path:
        f = tmp_path / "secrets.env"
        f.write_text("DB_PASSWORD=hunter2\nAPI_KEY=sk-123\n# comment\n\nEMPTY=\n")
        return f

    @pytest.fixture()
    def provider(self, secrets_file: Path) -> FileCredentialProvider:
        return FileCredentialProvider(secrets_file)

    @pytest.fixture()
    def db_grant(self) -> Grant:
        return Grant(resources=["credential:DB_PASSWORD"], actions=["read"])

    def test_satisfies_protocol(self, provider: FileCredentialProvider) -> None:
        assert isinstance(provider, CredentialProvider)

    async def test_returns_value_with_grant(
        self, provider: FileCredentialProvider, db_grant: Grant
    ) -> None:
        result = await provider.get("presidium://local/t", "DB_PASSWORD", [db_grant])
        assert result == "hunter2"

    async def test_returns_none_without_grant(self, provider: FileCredentialProvider) -> None:
        result = await provider.get("presidium://local/t", "DB_PASSWORD", [])
        assert result is None

    async def test_returns_none_for_missing_key(self, provider: FileCredentialProvider) -> None:
        grant = Grant(resources=["credential:NONEXISTENT"], actions=["read"])
        result = await provider.get("presidium://local/t", "NONEXISTENT", [grant])
        assert result is None

    async def test_skips_comments_and_blank_lines(self, provider: FileCredentialProvider) -> None:
        grant = Grant(resources=["credential:API_KEY"], actions=["read"])
        result = await provider.get("presidium://local/t", "API_KEY", [grant])
        assert result == "sk-123"

    async def test_handles_empty_value(self, provider: FileCredentialProvider) -> None:
        grant = Grant(resources=["credential:EMPTY"], actions=["read"])
        result = await provider.get("presidium://local/t", "EMPTY", [grant])
        assert result == ""

    async def test_missing_file_loads_empty(self, tmp_path: Path) -> None:
        provider = FileCredentialProvider(tmp_path / "nonexistent.env")
        grant = Grant(resources=["credential:X"], actions=["read"])
        result = await provider.get("presidium://local/t", "X", [grant])
        assert result is None

    async def test_close_clears_secrets(
        self, provider: FileCredentialProvider, db_grant: Grant
    ) -> None:
        await provider.close()
        result = await provider.get("presidium://local/t", "DB_PASSWORD", [db_grant])
        assert result is None

    async def test_case_insensitive_lookup(self, provider: FileCredentialProvider) -> None:
        grant = Grant(resources=["credential:db_password"], actions=["read"])
        result = await provider.get("presidium://local/t", "db_password", [grant])
        assert result == "hunter2"
