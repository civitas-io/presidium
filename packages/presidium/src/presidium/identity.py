"""Identity binding for AgentRecord.public_key -- Ed25519 (default, real,
shipped) and EC P-256 (real, additive, for presidium-contrib[spiffe]).

Presidium does not generate or hold private key material itself — it reuses
Civitas's own real Ed25519 identity machinery (``civitas.security.identity.
AgentIdentity``) by default, which already provisions and persists per-agent
keypairs. This module provides the one, shared, pure-function verification
primitive every ``AgentRegistry`` implementation delegates to, so the crypto
handling lives in exactly one place rather than being re-derived per backend
(``InMemoryRegistry``, ``SqliteRegistry``, ``presidium-contrib``'s
``PostgresAgentRegistry``).

Real, current scope (2026-08-22): this closes the gap where
``GovernedRuntime.start()`` previously hardcoded ``AgentRecord(public_key="",
...)`` — a real, documented-as-delivered-but-never-implemented M2 claim (see
``docs/vision/roadmap.md``'s Implementation Priority section). It does not
attempt to duplicate Civitas's own transport-level message signing
(``civitas.security.signing.MessageSigner``) — that is a distinct concern
(signing messages on the bus) from this module's concern (Presidium's own
registry being able to verify an ad-hoc claim against a stored public key).

2026-08-24: dispatches on the new ``AgentRecord.public_key_algorithm`` field
(default ``"ed25519"``, unchanged behavior for every existing caller) to add
a real ``"ec_p256"`` path — SPIRE's own default X.509-SVID key type,
confirmed directly against a real SVID in SPIFFE's own docs (see
``docs/design/spiffe-vendor-research-2026-08.md``), needed because a real
SPIFFE identity's public key is not Ed25519 by default. Uses the
``cryptography`` library, lazily imported exactly like ``pynacl`` is below
— not a new required core dependency, but one that's already guaranteed
present whenever ``presidium-contrib[spiffe]`` is installed (``spiffe``
itself depends on ``cryptography>=46``, confirmed directly).
"""

from __future__ import annotations

import base64
import logging

from presidium.model import AgentRecord

logger = logging.getLogger(__name__)


def verify_agent_signature(record: AgentRecord | None, data: bytes, signature: bytes) -> bool:
    """Verify ``signature`` over ``data`` against ``record``'s stored public key.

    Returns ``False`` — never raises — for every failure case: ``record`` is
    ``None`` (unknown agent), an empty/missing ``public_key`` (never bound,
    e.g. a record constructed without going through ``GovernedRuntime.start()``
    or an explicit identity), a malformed ``public_key`` (not valid base64, or
    not a 32-byte Ed25519 verify key), or a genuinely invalid signature.
    Matches the same fail-closed-as-a-plain-return-value shape as
    ``AgentRegistry.has_grant()`` — a caller is forced to check the boolean,
    never accidentally treats a raised exception as permissive via a broad
    ``except:`` upstream.
    """
    if record is None or not record.public_key:
        return False

    if record.public_key_algorithm == "ec_p256":
        return _verify_ec_p256(record, data, signature)
    return _verify_ed25519(record, data, signature)


def _verify_ed25519(record: AgentRecord, data: bytes, signature: bytes) -> bool:
    try:
        import nacl.exceptions
        import nacl.signing
    except ImportError:
        logger.warning(
            "identity.verify_unavailable agent=%s reason=pynacl_not_installed",
            record.name,
        )
        return False

    try:
        key_bytes = base64.b64decode(record.public_key, validate=True)
        verify_key = nacl.signing.VerifyKey(key_bytes)
        verify_key.verify(data, signature)
    except (ValueError, nacl.exceptions.BadSignatureError, nacl.exceptions.CryptoError):
        return False

    return True


def _verify_ec_p256(record: AgentRecord, data: bytes, signature: bytes) -> bool:
    """Verifies an ECDSA/P-256/SHA-256 signature -- the real, confirmed shape of a
    SPIRE-issued X.509-SVID's default key type. ``record.public_key`` holds the
    raw, uncompressed EC point bytes (``Encoding.X962``/``PublicFormat.UncompressedPoint``,
    the same encoding ``presidium_contrib.spiffe`` extracts on the issuing side) --
    not a PEM/DER certificate; this function verifies a raw signature against an
    already-extracted key, it does not perform X.509 chain validation (that happens
    once, when a SPIFFE-backed agent's identity is registered/rotated -- see
    docs/design/spiffe-vendor-research-2026-08.md §4).
    """
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.hashes import SHA256
    except ImportError:
        logger.warning(
            "identity.verify_unavailable agent=%s reason=cryptography_not_installed",
            record.name,
        )
        return False

    try:
        key_bytes = base64.b64decode(record.public_key, validate=True)
        public_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), key_bytes)
        public_key.verify(signature, data, ec.ECDSA(SHA256()))
    except (ValueError, InvalidSignature):
        return False

    return True
