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


def _record_with_key(public_key: str, algorithm: str = "ed25519") -> AgentRecord:
    return AgentRecord(
        agent_id="presidium://local/researcher",
        name="researcher",
        public_key=public_key,
        public_key_algorithm=algorithm,  # type: ignore[arg-type]
    )


def _generate_ec_p256_keypair() -> tuple[object, str]:
    """Real EC P-256 keypair, matching the exact encoding
    presidium_contrib.spiffe extracts from a real SVID leaf cert --
    uncompressed point, Encoding.X962/PublicFormat.UncompressedPoint."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_bytes = private_key.public_key().public_bytes(
        Encoding.X962, PublicFormat.UncompressedPoint
    )
    return private_key, base64.b64encode(public_bytes).decode()


def _sign_ec_p256(private_key: object, data: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.hashes import SHA256

    return private_key.sign(data, ec.ECDSA(SHA256()))  # type: ignore[attr-defined]


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


class TestVerifyAgentSignatureEcP256:
    """Real EC P-256 tests -- presidium-contrib[spiffe]'s key type,
    confirmed against a real SPIRE SVID's default (docs/design/
    spiffe-vendor-research-2026-08.md). Mirrors TestVerifyAgentSignature's
    own Ed25519 coverage shape, applied to the new algorithm.
    """

    def test_valid_signature_verifies(self) -> None:
        private_key, public_key_b64 = _generate_ec_p256_keypair()
        data = b"do the thing"
        signature = _sign_ec_p256(private_key, data)
        record = _record_with_key(public_key_b64, algorithm="ec_p256")

        assert verify_agent_signature(record, data, signature) is True

    def test_tampered_data_fails(self) -> None:
        private_key, public_key_b64 = _generate_ec_p256_keypair()
        signature = _sign_ec_p256(private_key, b"do the thing")
        record = _record_with_key(public_key_b64, algorithm="ec_p256")

        assert verify_agent_signature(record, b"do a different thing", signature) is False

    def test_wrong_signer_key_fails(self) -> None:
        signer_private, signer_public_b64 = _generate_ec_p256_keypair()
        impostor_private, _ = _generate_ec_p256_keypair()
        data = b"do the thing"
        signature = _sign_ec_p256(impostor_private, data)
        record = _record_with_key(signer_public_b64, algorithm="ec_p256")

        assert verify_agent_signature(record, data, signature) is False

    def test_ed25519_signature_rejected_against_ec_p256_record(self) -> None:
        """Real cross-algorithm confusion guard: an Ed25519 signature must
        never validate against a record declaring ec_p256 -- proves the
        dispatch is real, not a fallthrough that tries both."""
        from civitas.security.identity import AgentIdentity

        _, public_key_b64 = _generate_ec_p256_keypair()
        identity = AgentIdentity.generate("researcher")
        ed25519_signature = identity.sign(b"do the thing")
        record = _record_with_key(public_key_b64, algorithm="ec_p256")

        assert verify_agent_signature(record, b"do the thing", ed25519_signature) is False

    def test_malformed_key_returns_false_not_raises(self) -> None:
        record = _record_with_key(base64.b64encode(b"too-short").decode(), algorithm="ec_p256")
        assert verify_agent_signature(record, b"data", b"sig") is False

    def test_cryptography_unavailable_returns_false_not_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Defensive path, mirroring the pynacl-unavailable test above.

        The real keypair must be generated BEFORE the fake-import patch is
        installed -- generating it needs the very same `cryptography`
        import this test is about to block, a real ordering bug caught
        while writing this test, not after.
        """
        _, public_key_b64 = _generate_ec_p256_keypair()
        record = _record_with_key(public_key_b64, algorithm="ec_p256")

        import builtins

        real_import = builtins.__import__

        def _fake_import(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("cryptography"):
                raise ImportError(f"simulated missing dependency: {name}")
            return real_import(name, *args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(builtins, "__import__", _fake_import)

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
async def test_registry_update_identity_end_to_end(registry_cls_name: str) -> None:
    """Full path: register with Ed25519 -> update_identity() to a real EC
    P-256 key (rotation, e.g. presidium-contrib[spiffe]) -> verify_signature()
    uses the NEW key/algorithm, not the old one -- a real, end-to-end proof
    that update_identity() actually persists on both backends, not just
    returns a value.
    """
    from presidium.registry.memory import InMemoryRegistry
    from presidium.registry.sqlite import SqliteRegistry

    old_identity = AgentIdentity.generate("researcher")
    record = AgentRecord(
        agent_id="presidium://local/researcher",
        name="researcher",
        public_key=old_identity.public_key_b64(),
    )

    registry = InMemoryRegistry() if registry_cls_name == "memory" else SqliteRegistry(":memory:")
    try:
        await registry.register(record)

        new_private_key, new_public_key_b64 = _generate_ec_p256_keypair()
        updated = await registry.update_identity(
            "researcher", new_public_key_b64, public_key_algorithm="ec_p256"
        )
        assert updated.public_key == new_public_key_b64
        assert updated.public_key_algorithm == "ec_p256"

        # A lookup (not the return value of update_identity itself) proves
        # the change was really persisted, not just returned in-memory.
        looked_up = await registry.lookup("researcher")
        assert looked_up is not None
        assert looked_up.public_key == new_public_key_b64
        assert looked_up.public_key_algorithm == "ec_p256"

        data = b"approve deployment"
        new_signature = _sign_ec_p256(new_private_key, data)
        old_signature = old_identity.sign(data)

        assert await registry.verify_signature("researcher", data, new_signature) is True
        # The OLD Ed25519 signature must no longer verify -- proves
        # verify_signature() is really reading the rotated key/algorithm,
        # not a stale cached one.
        assert await registry.verify_signature("researcher", data, old_signature) is False
    finally:
        if isinstance(registry, SqliteRegistry):
            await registry.close()


@pytest.mark.parametrize("registry_cls_name", ["memory", "sqlite"])
async def test_update_identity_unknown_agent_raises(registry_cls_name: str) -> None:
    from presidium.errors import AgentNotFoundError
    from presidium.registry.memory import InMemoryRegistry
    from presidium.registry.sqlite import SqliteRegistry

    registry = InMemoryRegistry() if registry_cls_name == "memory" else SqliteRegistry(":memory:")
    try:
        with pytest.raises(AgentNotFoundError):
            await registry.update_identity("ghost", "some-key")
    finally:
        if isinstance(registry, SqliteRegistry):
            await registry.close()


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
