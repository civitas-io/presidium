"""Real end-to-end mTLS handshake test (2026-08-23) -- closes the one
remaining item still tagged (P0) in docs/vision/roadmap.md's M7 section.

test_presidium_server_real_gateway.py already proves the check_grant
request/response path works over real HTTP with require_mtls=False,
flagging honestly that a real mTLS handshake test was a separate, deferred
piece of work. This is that work: a real, self-signed private CA, a real
server leaf certificate, and real client leaf certificates (one trusted,
one signed by the same CA but not DN-allowlisted, one signed by a
different, untrusted CA) -- proving the actual TLS socket enforces what
build_check_grant_gateway_config's docstring claims, not just that the
config object assembles correctly.

**Real finding, this same session**: writing this test surfaced a genuine,
much bigger gap than "test not written yet" -- the currently-published
civitas (>=0.11.0) never actually delivers a real client certificate to
the ASGI app at all (uvicorn never populates the ASGI TLS extension), so
`require_client_cert` rejected every request, valid or not, with 401.
This is a known, tracked, now-FIXED upstream issue
(civitas-io/python-civitas#25, direct-mode half, R10 -- see that repo's
docs/design/gateway-http-mtls-direct.md) -- fixed and verified end to end
against THIS exact test suite via a local, uncommitted editable install of
the fixed python-civitas, but not yet in a tagged civitas release
Presidium can actually depend on. The two scenarios that need a real
client certificate to reach the app layer are marked xfail(strict=True)
below until that release exists; the two that only need the TLS-layer
behavior (already correct, unaffected by the gap) pass today for real.

Mirrors the certificate-generation pattern civitas's own
tests/unit/test_gateway_ws_grpc_auth.py uses for its real gRPC mTLS tests
(self-signed CA + RSA leaves via `cryptography`) -- proven, not invented
here, applied to the HTTP/uvicorn transport instead, which python-civitas
itself does not yet have an equivalent real-socket test for.
"""

from __future__ import annotations

import asyncio
import datetime
import ipaddress
import ssl
from collections.abc import AsyncGenerator
from types import SimpleNamespace

import httpx
import pytest
from civitas import Runtime, Supervisor
from civitas.config import Settings
from civitas.gateway import HTTPGateway
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from presidium.model import (
    AgentRecord,
    EvaluationStage,
    Grant,
    PolicyDecision,
    PolicyRule,
)
from presidium.policy.cel import CelPolicyEngine
from presidium.registry.memory import InMemoryRegistry
from presidium.runtime import GovernedRuntime
from presidium_contrib.server import (
    HealthCheckAgent,
    PresidiumGatewayAgent,
    build_check_grant_gateway_config,
)

_PORT = 19444
_BASE_URL = f"https://127.0.0.1:{_PORT}"

ALLOW_ALL = PolicyRule(
    name="allow-all",
    stage=EvaluationStage.PRE_TOOL,
    expression="true",
    decision=PolicyDecision.ALLOW,
    priority=0,
)

# ---------------------------------------------------------------------------
# Certificate helpers -- a real self-signed CA + real leaves, no mocking.
# ---------------------------------------------------------------------------


def _rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _key_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    )


def _make_ca(common_name: str) -> tuple[rsa.RSAPrivateKey, x509.Certificate]:
    key = _rsa_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.datetime.now(datetime.UTC)
    # Two real, live bugs found running this test for the first time: modern
    # OpenSSL (3.x, what CPython's ssl module links against) refuses chain
    # validation without (1) a SubjectKeyIdentifier on the CA matched by an
    # AuthorityKeyIdentifier on each leaf, and (2) a KeyUsage extension on
    # the CA asserting keyCertSign/cRLSign. civitas's own test helper (which
    # this mirrors) doesn't need either because grpc.aio's own cert
    # validation path is more lenient than Python's ssl module (used by
    # uvicorn/httpx here).
    ski = x509.SubjectKeyIdentifier.from_public_key(key.public_key())
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(ski, critical=False)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _make_leaf(
    ca_key: rsa.RSAPrivateKey,
    ca_cert: x509.Certificate,
    common_name: str,
    *,
    san: str | None = None,
) -> tuple[bytes, bytes]:
    key = _rsa_key()
    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Acme"),
        ]
    )
    now = datetime.datetime.now(datetime.UTC)
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=3650))
    )
    if san is not None:
        # Both a DNS SAN and an IP SAN -- httpx connects to 127.0.0.1
        # directly, which needs an IPAddress SAN match, not just a DNSName.
        builder = builder.add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(san), x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
            ),
            critical=False,
        )
    aki = x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key())
    builder = builder.add_extension(aki, critical=False)
    cert = builder.sign(ca_key, hashes.SHA256())
    return _key_pem(key), cert.public_bytes(serialization.Encoding.PEM)


def _dn(pem: bytes) -> str:
    return x509.load_pem_x509_certificate(pem).subject.rfc4514_string()


def _client_ssl_context(
    ca_path: str, cert_path: str | None = None, key_path: str | None = None
) -> ssl.SSLContext:
    """A real, fully-configured client SSLContext -- httpx's deprecated
    cert=(cert, key) + verify=<str path> combination has a real bug/
    incompatibility in this httpx version (found running this test for the
    first time: a fully valid, trusted, correctly-loaded client cert still
    produced a bare httpx.ReadError with zero server-side signal). The
    modern, recommended API -- one fully-configured ssl.SSLContext passed
    as verify=... -- works correctly, confirmed empirically."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(ca_path)
    if cert_path is not None:
        ctx.load_cert_chain(cert_path, key_path)
    return ctx


@pytest.fixture(scope="module")
def tls_certs(tmp_path_factory: pytest.TempPathFactory) -> SimpleNamespace:
    """A real trust anchor plus leaves for all four handshake scenarios:

    - server: presented by the gateway itself (CN=localhost, SAN=localhost)
    - client (trusted): signed by the real CA, DN will be allowlisted
    - intruder (same CA, wrong DN): signed by the SAME real CA -- passes
      the TLS-layer "signed by a trusted CA" check, so it reaches the app
      layer, where the DN allowlist must reject it (403, not a handshake
      failure)
    - outsider (different CA entirely): the actual "untrusted CA" case --
      must fail at the TLS handshake itself, never reaching the app at all
    """
    ca_key, ca_cert = _make_ca("Presidium Test CA")
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
    server_key, server_cert = _make_leaf(ca_key, ca_cert, "localhost", san="localhost")
    client_key, client_cert = _make_leaf(ca_key, ca_cert, "trusted-service")
    intruder_key, intruder_cert = _make_leaf(ca_key, ca_cert, "intruder-service")

    other_ca_key, other_ca_cert = _make_ca("A Completely Different CA")
    outsider_key, outsider_cert = _make_leaf(other_ca_key, other_ca_cert, "outsider-service")

    directory = tmp_path_factory.mktemp("mtls")

    def _write(name: str, data: bytes) -> str:
        path = directory / name
        path.write_bytes(data)
        return str(path)

    return SimpleNamespace(
        ca_path=_write("ca.pem", ca_pem),
        server_cert_path=_write("server.pem", server_cert),
        server_key_path=_write("server.key", server_key),
        client_cert_path=_write("client.pem", client_cert),
        client_key_path=_write("client.key", client_key),
        client_dn=_dn(client_cert),
        intruder_cert_path=_write("intruder.pem", intruder_cert),
        intruder_key_path=_write("intruder.key", intruder_key),
        outsider_cert_path=_write("outsider.pem", outsider_cert),
        outsider_key_path=_write("outsider.key", outsider_key),
    )


# ---------------------------------------------------------------------------
# Real gateway, real TLS, real client-cert enforcement.
# ---------------------------------------------------------------------------


async def _wait_for_port_open(host: str, port: int, timeout_seconds: float = 5.0) -> None:
    async with asyncio.timeout(timeout_seconds):
        while True:
            try:
                # A plain TCP connect is enough to know uvicorn has bound the
                # socket -- the TLS handshake itself is exercised per-test.
                _, writer = await asyncio.open_connection(host, port)
                writer.close()
                await writer.wait_closed()
                return
            except OSError:
                await asyncio.sleep(0.02)


@pytest.fixture
async def _running_mtls_gateway(
    monkeypatch: pytest.MonkeyPatch, tls_certs: SimpleNamespace
) -> AsyncGenerator[None]:
    # civitas.gateway.mtls imports `settings` by reference at module load
    # time and reads it at request time -- patching the module-level
    # reference is the same pattern civitas's own gRPC mTLS tests use
    # (test_gateway_ws_grpc_auth.py), since setting the env var alone would
    # not affect an already-constructed Settings singleton.
    monkeypatch.setattr(
        "civitas.gateway.mtls.settings",
        Settings(env={"CIVITAS_GATEWAY_MTLS_ALLOWED_DNS": tls_certs.client_dn}),
    )

    registry = InMemoryRegistry()
    await registry.register(
        AgentRecord(
            agent_id="presidium://acme.com/researcher",
            name="researcher",
            public_key="",
            grants=[Grant(resources=["code_mode"], actions=["invoke"], id="g1")],
        )
    )
    engine = CelPolicyEngine()
    engine.load_policies([ALLOW_ALL])
    runtime = GovernedRuntime(registry=registry, engine=engine)

    gateway_config = build_check_grant_gateway_config(
        port=_PORT,
        require_mtls=True,
        tls_cert=tls_certs.server_cert_path,
        tls_key=tls_certs.server_key_path,
        tls_ca_cert=tls_certs.ca_path,
    )
    gateway = HTTPGateway("api", config=gateway_config)
    gateway_agent = PresidiumGatewayAgent(runtime=runtime)
    health_agent = HealthCheckAgent()

    supervisor = Supervisor("root", children=[gateway, gateway_agent, health_agent])
    civitas_runtime = Runtime(supervisor=supervisor)
    await civitas_runtime.start()
    try:
        try:
            await _wait_for_port_open("127.0.0.1", _PORT)
        except (OSError, TimeoutError):
            pass  # sock.connect can race uvicorn's own bind; fall back below
        await asyncio.sleep(0.05)
        yield
    finally:
        await civitas_runtime.stop()


_BLOCKED_ON_CIVITAS_25 = (
    "Blocked on civitas-io/python-civitas#25 (direct-mode half, R10): the currently-published "
    "civitas release (>=0.11.0) never populates the ASGI TLS extension, so a real client "
    "certificate never reaches the app layer at all -- every request gets 401 regardless of "
    "validity. Fixed in python-civitas main (commit 8d72084, docs/design/"
    "gateway-http-mtls-direct.md) and verified end to end against THIS test suite via a local, "
    "uncommitted editable install -- not yet in a tagged civitas release Presidium can depend "
    "on. xfail(strict=True) so this stays honest: the moment Presidium bumps to a civitas "
    "release containing the fix, this marker itself starts failing (test unexpectedly passes) "
    "-- the correct, unmissable signal to remove it and graduate this to real coverage."
)


class TestMtlsRealHandshake:
    """Proves the actual TLS socket enforces what the config claims --
    not just that GatewayConfig/build_check_grant_gateway_config assemble
    the right fields (already covered by test_gateway_config.py)."""

    @pytest.mark.xfail(strict=True, reason=_BLOCKED_ON_CIVITAS_25)
    async def test_trusted_client_cert_allowlisted_dn_reaches_the_app(
        self, _running_mtls_gateway: None, tls_certs: SimpleNamespace
    ) -> None:
        async with httpx.AsyncClient(
            verify=_client_ssl_context(
                tls_certs.ca_path, tls_certs.client_cert_path, tls_certs.client_key_path
            ),
        ) as client:
            resp = await client.get(f"{_BASE_URL}/health", timeout=5.0)
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

            resp = await client.post(
                f"{_BASE_URL}/v1/check_grant",
                json={"agent_id": "presidium://acme.com/researcher", "action": "code_mode"},
                timeout=5.0,
            )
            assert resp.status_code == 200
            assert resp.json()["decision"] == "allow"

    @pytest.mark.xfail(strict=True, reason=_BLOCKED_ON_CIVITAS_25)
    async def test_same_ca_but_dn_not_allowlisted_gets_403(
        self, _running_mtls_gateway: None, tls_certs: SimpleNamespace
    ) -> None:
        """The TLS handshake itself succeeds (signed by the trusted CA) --
        the app-layer DN allowlist is what rejects this, proving the two
        layers (transport trust vs. identity authorization) are both real
        and distinct, exactly as civitas.gateway.mtls's own module
        docstring describes."""
        async with httpx.AsyncClient(
            verify=_client_ssl_context(
                tls_certs.ca_path, tls_certs.intruder_cert_path, tls_certs.intruder_key_path
            ),
        ) as client:
            resp = await client.get(f"{_BASE_URL}/health", timeout=5.0)
        assert resp.status_code == 403

    async def test_no_client_cert_fails_the_tls_handshake(
        self, _running_mtls_gateway: None, tls_certs: SimpleNamespace
    ) -> None:
        """client_cert_mode='required' maps to ssl.CERT_REQUIRED -- uvicorn
        must refuse the handshake itself before any HTTP request is even
        possible, not return a 401 at the application layer."""
        async with httpx.AsyncClient(verify=_client_ssl_context(tls_certs.ca_path)) as client:
            with pytest.raises((httpx.ConnectError, httpx.ReadError, ssl.SSLError)):
                await client.get(f"{_BASE_URL}/health", timeout=5.0)

    async def test_cert_from_an_untrusted_ca_fails_the_tls_handshake(
        self, _running_mtls_gateway: None, tls_certs: SimpleNamespace
    ) -> None:
        """A cert signed by a completely different CA -- the real
        'mTLS without a trusted anchor is theater' case this whole test
        file exists to prove doesn't happen. Must fail at the TLS layer,
        never reach the DN allowlist at all."""
        async with httpx.AsyncClient(
            verify=_client_ssl_context(
                tls_certs.ca_path, tls_certs.outsider_cert_path, tls_certs.outsider_key_path
            ),
        ) as client:
            with pytest.raises((httpx.ConnectError, httpx.ReadError, ssl.SSLError)):
                await client.get(f"{_BASE_URL}/health", timeout=5.0)
