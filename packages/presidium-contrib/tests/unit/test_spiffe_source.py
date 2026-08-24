"""Real, pure-function tests for presidium_contrib.spiffe.source's key
extraction -- no real SPIRE server needed for these (unlike
tests/integration/test_spiffe_real_server.py), since _extract_public_key()
only needs a real `cryptography` keypair object, not a live Workload API
connection.
"""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from presidium_contrib.spiffe.source import UnsupportedSpiffeKeyTypeError, _extract_public_key


class TestExtractPublicKey:
    def test_ec_p256_key_extracted_correctly(self) -> None:
        private_key = ec.generate_private_key(ec.SECP256R1())
        public_key = private_key.public_key()

        algorithm, key_b64 = _extract_public_key(public_key)

        assert algorithm == "ec_p256"
        expected_raw = public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        assert base64.b64decode(key_b64) == expected_raw

    def test_ed25519_key_extracted_correctly(self) -> None:
        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        algorithm, key_b64 = _extract_public_key(public_key)

        assert algorithm == "ed25519"
        expected_raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        assert base64.b64decode(key_b64) == expected_raw
        assert len(base64.b64decode(key_b64)) == 32

    def test_ec_p384_key_rejected(self) -> None:
        """A real, different EC curve (not SPIRE's own default P-256) must
        be rejected, not silently mislabeled as ec_p256 -- proves the
        isinstance(curve, ec.SECP256R1) check is real, not just
        isinstance(key, EllipticCurvePublicKey)."""
        private_key = ec.generate_private_key(ec.SECP384R1())

        with pytest.raises(UnsupportedSpiffeKeyTypeError) as exc_info:
            _extract_public_key(private_key.public_key())

        assert "Unsupported SPIFFE SVID key type" in str(exc_info.value)

    def test_rsa_key_rejected(self) -> None:
        """A real RSA key (a real, valid SPIRE KeyManager option) must be
        rejected with a clear, actionable error, not silently mishandled."""
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        with pytest.raises(UnsupportedSpiffeKeyTypeError) as exc_info:
            _extract_public_key(private_key.public_key())

        assert exc_info.value.key_type is not None
        assert "presidium-contrib[spiffe] currently supports EC P-256 only" in str(exc_info.value)
