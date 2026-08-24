"""Real end-to-end test: SpiffeIdentitySource + bind_identity_to_registry
against an actual running SPIRE server + agent -- not mocked.

Gated on a real Workload API Unix socket being reachable, matching this
org's own established hardware-gating precedent (fabrica's own
`_srt_available` pattern for `srt`-dependent tests): most dev machines and
CI runners don't have a real SPIRE server running, so this test is skipped
there, not faked. Verified for real on the homelab against a genuine SPIRE
v1.15.3 server + agent (see docs/design/spiffe-vendor-research-2026-08.md
for the setup) -- a real registration entry, a real X.509-SVID fetch, a
real EC P-256 leaf certificate confirmed directly (not assumed).

To run for real: set PRESIDIUM_SPIFFE_TEST_SOCKET to a real Workload API
socket path (e.g. unix:///tmp/spire-agent/public/api.sock) with a real,
already-registered SPIFFE ID reachable through it.
"""

from __future__ import annotations

import os

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.hashes import SHA256

from presidium.model import AgentRecord
from presidium.registry.memory import InMemoryRegistry
from presidium_contrib.spiffe.binding import bind_identity_to_registry
from presidium_contrib.spiffe.source import SpiffeIdentitySource

_SOCKET_PATH = os.environ.get("PRESIDIUM_SPIFFE_TEST_SOCKET")

_requires_real_socket = pytest.mark.skipif(
    not _SOCKET_PATH,
    reason="PRESIDIUM_SPIFFE_TEST_SOCKET not set -- no real SPIRE Workload API to test against",
)


@_requires_real_socket
class TestSpiffeIdentitySourceRealServer:
    async def test_start_fetches_a_real_svid(self) -> None:
        assert _SOCKET_PATH is not None
        source = SpiffeIdentitySource(_SOCKET_PATH, timeout_in_seconds=5)
        try:
            await source.start()
            assert source.agent_id.startswith("presidium://")
            assert source.public_key_algorithm == "ec_p256"
            # A real, base64-decodable, non-empty key -- not a placeholder.
            import base64

            decoded = base64.b64decode(source.public_key_b64)
            assert len(decoded) > 0
        finally:
            source.close()

    async def test_start_is_idempotent(self) -> None:
        assert _SOCKET_PATH is not None
        source = SpiffeIdentitySource(_SOCKET_PATH, timeout_in_seconds=5)
        try:
            await source.start()
            first_agent_id = source.agent_id
            await source.start()  # must not raise, not re-fetch a different SVID
            assert source.agent_id == first_agent_id
        finally:
            source.close()


def test_property_access_before_start_raises_without_needing_a_real_socket() -> None:
    """Deliberately NOT under _requires_real_socket -- this is a pure
    precondition check, it never touches the Workload API at all, so it
    should run everywhere, not be over-skipped alongside the tests that
    genuinely need a real SPIRE server.
    """
    from presidium.errors import PresidiumError

    source = SpiffeIdentitySource("unix:///nonexistent.sock")
    with pytest.raises(PresidiumError, match="start\\(\\) must be awaited"):
        _ = source.agent_id


@_requires_real_socket
class TestBindIdentityToRegistryRealServer:
    async def test_binds_real_identity_into_registry(self) -> None:
        assert _SOCKET_PATH is not None
        registry = InMemoryRegistry()
        await registry.register(
            AgentRecord(
                agent_id="presidium://local/researcher",
                name="researcher",
                public_key="",
            )
        )

        source = SpiffeIdentitySource(_SOCKET_PATH, timeout_in_seconds=5)
        try:
            await source.start()
            await bind_identity_to_registry(source, registry, "researcher")

            record = await registry.lookup("researcher")
            assert record is not None
            assert record.public_key == source.public_key_b64
            assert record.public_key_algorithm == "ec_p256"

            # A real signature made with the SVID's own private key must
            # verify against what the registry now has stored -- proves
            # the whole real chain (SPIRE -> SpiffeIdentitySource ->
            # AgentRegistry.update_identity -> verify_agent_signature)
            # works end to end, not just that fields got copied.
            from presidium.identity import verify_agent_signature

            svid = source._require_started().get_x509_context().default_svid  # noqa: SLF001
            data = b"approve deployment"
            signature = svid.private_key.sign(data, ec.ECDSA(SHA256()))

            assert verify_agent_signature(record, data, signature) is True
        finally:
            source.close()

    async def test_bind_unknown_agent_raises(self) -> None:
        from presidium.errors import AgentNotFoundError

        assert _SOCKET_PATH is not None
        registry = InMemoryRegistry()
        source = SpiffeIdentitySource(_SOCKET_PATH, timeout_in_seconds=5)
        try:
            await source.start()
            with pytest.raises(AgentNotFoundError):
                await bind_identity_to_registry(source, registry, "ghost")
        finally:
            source.close()
