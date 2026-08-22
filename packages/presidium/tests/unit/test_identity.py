"""Real tests for the Ed25519 identity binding fix (2026-08-22).

Covers `presidium.identity.verify_agent_signature` directly (the shared
primitive every `AgentRegistry` backend delegates to) using real Civitas
`AgentIdentity` keypairs -- not mocked crypto.
"""

from __future__ import annotations

import base64

import pytest
from civitas.security.identity import AgentIdentity

from presidium.identity import verify_agent_signature
from presidium.model import AgentRecord


def _record_with_key(public_key: str) -> AgentRecord:
    return AgentRecord(
        agent_id="presidium://local/researcher",
        name="researcher",
        public_key=public_key,
    )


class TestVerifyAgentSignature:
    def test_valid_signature_verifies(self, tmp_path: object) -> None:
        identity = AgentIdentity.generate("researcher")
        data = b"do the thing"
        signature = identity.sign(data)
        record = _record_with_key(identity.public_key_b64())

        assert verify_agent_signature(record, data, signature) is True

    def test_tampered_data_fails(self) -> None:
        identity = AgentIdentity.generate("researcher")
        signature = identity.sign(b"do the thing")
        record = _record_with_key(identity.public_key_b64())

        assert verify_agent_signature(record, b"do a different thing", signature) is False

    def test_wrong_signer_key_fails(self) -> None:
        signer = AgentIdentity.generate("researcher")
        impostor = AgentIdentity.generate("impostor")
        data = b"do the thing"
        signature = impostor.sign(data)
        # record claims to be `signer`'s public key, but the signature was
        # produced by `impostor`'s private key -- must not verify.
        record = _record_with_key(signer.public_key_b64())

        assert verify_agent_signature(record, data, signature) is False

    def test_unknown_agent_record_none_returns_false_not_raises(self) -> None:
        assert verify_agent_signature(None, b"data", b"sig") is False

    def test_empty_public_key_returns_false(self) -> None:
        record = _record_with_key("")
        assert verify_agent_signature(record, b"data", b"sig") is False

    def test_malformed_base64_returns_false_not_raises(self) -> None:
        record = _record_with_key("not valid base64!!!")
        assert verify_agent_signature(record, b"data", b"sig") is False

    def test_wrong_length_key_returns_false_not_raises(self) -> None:
        # Valid base64, but not a 32-byte Ed25519 verify key.
        record = _record_with_key(base64.b64encode(b"too-short").decode())
        assert verify_agent_signature(record, b"data", b"sig") is False

    def test_empty_signature_returns_false_not_raises(self) -> None:
        identity = AgentIdentity.generate("researcher")
        record = _record_with_key(identity.public_key_b64())
        assert verify_agent_signature(record, b"data", b"") is False

    def test_pynacl_unavailable_returns_false_not_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defensive path: even though pynacl is a hard presidium dependency,
        a broken install (e.g. missing native libsodium) must fail closed as
        a plain False, not an uncaught ImportError bubbling out of a policy
        check.
        """
        import builtins

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name in ("nacl.signing", "nacl.exceptions"):
                raise ImportError(f"simulated missing dependency: {name}")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", _fake_import)

        record = _record_with_key(base64.b64encode(b"x" * 32).decode())
        assert verify_agent_signature(record, b"data", b"sig") is False


class TestAgentIdentityPersistence:
    """Real, on-disk persistence -- proves `load_or_generate` round-trips."""

    def test_same_name_same_key_dir_loads_same_identity(self, tmp_path: object) -> None:
        first = AgentIdentity.load_or_generate("researcher", tmp_path)  # type: ignore[arg-type]
        second = AgentIdentity.load_or_generate("researcher", tmp_path)  # type: ignore[arg-type]

        assert first.public_key_b64() == second.public_key_b64()

    def test_different_names_get_different_keys(self, tmp_path: object) -> None:
        researcher = AgentIdentity.load_or_generate("researcher", tmp_path)  # type: ignore[arg-type]
        writer = AgentIdentity.load_or_generate("writer", tmp_path)  # type: ignore[arg-type]

        assert researcher.public_key_b64() != writer.public_key_b64()

    def test_public_key_is_32_real_bytes_when_decoded(self) -> None:
        identity = AgentIdentity.generate("researcher")
        decoded = base64.b64decode(identity.public_key_b64())
        assert len(decoded) == 32


@pytest.mark.parametrize("registry_cls_name", ["memory", "sqlite"])
async def test_registry_verify_signature_end_to_end(registry_cls_name: str) -> None:
    """Full path: real identity -> registry.register() -> registry.verify_signature()."""
    from presidium.registry.memory import InMemoryRegistry
    from presidium.registry.sqlite import SqliteRegistry

    identity = AgentIdentity.generate("researcher")
    record = AgentRecord(
        agent_id="presidium://local/researcher",
        name="researcher",
        public_key=identity.public_key_b64(),
    )

    registry = InMemoryRegistry() if registry_cls_name == "memory" else SqliteRegistry(":memory:")
    try:
        await registry.register(record)

        data = b"approve deployment"
        signature = identity.sign(data)

        assert await registry.verify_signature("researcher", data, signature) is True
        assert await registry.verify_signature("researcher", b"different data", signature) is False
        assert await registry.verify_signature("unknown-agent", data, signature) is False
    finally:
        if isinstance(registry, SqliteRegistry):
            await registry.close()
