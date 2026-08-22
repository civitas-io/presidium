"""Ed25519 identity binding for AgentRecord.public_key.

Presidium does not generate or hold private key material itself — it reuses
Civitas's own real Ed25519 identity machinery (``civitas.security.identity.
AgentIdentity``), which already provisions and persists per-agent keypairs.
This module provides the one, shared, pure-function verification primitive
every ``AgentRegistry`` implementation delegates to, so the crypto handling
lives in exactly one place rather than being re-derived per backend
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
