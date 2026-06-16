from __future__ import annotations

from presidium_contrib.mcp_gateway.pii import PIIDetector
from presidium_contrib.mcp_gateway.poisoning import PoisoningDetector, PoisoningStatus
from presidium_contrib.mcp_gateway.redaction import redact_dict, redact_string


class TestPoisoningDetector:
    def test_unapproved_tool(self) -> None:
        detector = PoisoningDetector()
        result = detector.check("db_query", "Query the database", {"sql": "string"})
        assert result.status == PoisoningStatus.UNAPPROVED

    def test_approved_tool_is_clean(self) -> None:
        detector = PoisoningDetector()
        detector.approve_tool("db_query", "Query the database", {"sql": "string"}, "admin@co.com")
        result = detector.check("db_query", "Query the database", {"sql": "string"})
        assert result.status == PoisoningStatus.CLEAN

    def test_description_changed(self) -> None:
        detector = PoisoningDetector()
        detector.approve_tool("db_query", "Query the database", {"sql": "string"}, "admin@co.com")
        result = detector.check("db_query", "Execute arbitrary SQL", {"sql": "string"})
        assert result.status == PoisoningStatus.DESCRIPTION_CHANGED

    def test_parameters_changed(self) -> None:
        detector = PoisoningDetector()
        detector.approve_tool("db_query", "Query the database", {"sql": "string"}, "admin@co.com")
        result = detector.check(
            "db_query", "Query the database", {"sql": "string", "admin": "bool"}
        )
        assert result.status == PoisoningStatus.PARAMETERS_CHANGED

    def test_revoke_tool(self) -> None:
        detector = PoisoningDetector()
        detector.approve_tool("db_query", "Query the database", {"sql": "string"}, "admin@co.com")
        assert detector.revoke("db_query") is True
        result = detector.check("db_query", "Query the database", {"sql": "string"})
        assert result.status == PoisoningStatus.UNAPPROVED

    def test_revoke_nonexistent(self) -> None:
        detector = PoisoningDetector()
        assert detector.revoke("nonexistent") is False

    def test_approve_returns_snapshot(self) -> None:
        detector = PoisoningDetector()
        snapshot = detector.approve_tool(
            "db_query", "Query the database", {"sql": "string"}, "admin@co.com"
        )
        assert snapshot.name == "db_query"
        assert snapshot.approved_by == "admin@co.com"
        assert len(snapshot.description_hash) == 64
        assert len(snapshot.parameters_hash) == 64


class TestCredentialRedaction:
    def test_redact_api_key(self) -> None:
        text = "api_key: sk-1234567890abcdef1234567890abcdef"
        result = redact_string(text)
        assert "sk-1234567890" not in result
        assert "**REDACTED**" in result

    def test_redact_bearer_token(self) -> None:
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9"
        result = redact_string(text)
        assert "eyJ" not in result

    def test_redact_aws_key(self) -> None:
        text = "key=AKIAIOSFODNN7EXAMPLE"
        result = redact_string(text)
        assert "AKIAIOSFODNN7EXAMPLE" not in result

    def test_redact_dict_sensitive_keys(self) -> None:
        data = {"api_key": "secret123", "name": "test", "password": "hunter2"}
        result = redact_dict(data)
        assert result["api_key"] == "**REDACTED**"
        assert result["password"] == "**REDACTED**"
        assert result["name"] == "test"

    def test_redact_dict_nested(self) -> None:
        data = {"config": {"token": "abc123", "host": "localhost"}}
        result = redact_dict(data)
        assert result["config"]["token"] == "**REDACTED**"
        assert result["config"]["host"] == "localhost"

    def test_redact_preserves_non_sensitive(self) -> None:
        text = "Hello world, this is a normal string"
        assert redact_string(text) == text

    def test_redact_github_pat(self) -> None:
        text = "token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh"
        result = redact_string(text)
        assert "ghp_" not in result


class TestPIIDetector:
    def test_detect_ssn(self) -> None:
        detector = PIIDetector()
        result = detector.scan_string("SSN: 123-45-6789")
        assert result.contains_pii is True
        assert "ssn" in result.pattern_names

    def test_detect_email(self) -> None:
        detector = PIIDetector()
        result = detector.scan_string("Contact: alice@example.com")
        assert result.contains_pii is True
        assert "email" in result.pattern_names

    def test_no_pii(self) -> None:
        detector = PIIDetector()
        result = detector.scan_string("This is a normal string with no PII")
        assert result.contains_pii is False
        assert len(result.matches) == 0

    def test_scan_dict(self) -> None:
        detector = PIIDetector()
        result = detector.scan_dict(
            {
                "user": {"email": "bob@example.com", "age": 30},
                "notes": "Contact at 123-45-6789",
            }
        )
        assert result.contains_pii is True
        assert "email" in result.pattern_names
        assert "ssn" in result.pattern_names

    def test_mask_string(self) -> None:
        detector = PIIDetector()
        masked = detector.mask_string("SSN: 123-45-6789, email: test@test.com")
        assert "123-45-6789" not in masked
        assert "test@test.com" not in masked
        assert "***" in masked

    def test_mask_dict(self) -> None:
        detector = PIIDetector()
        data = {"email": "alice@example.com", "count": 42}
        masked = detector.mask_dict(data)
        assert "alice@example.com" not in masked["email"]
        assert masked["count"] == 42

    def test_enabled_patterns_filter(self) -> None:
        detector = PIIDetector(enabled_patterns=["ssn"])
        result = detector.scan_string("SSN: 123-45-6789, email: test@test.com")
        assert result.contains_pii is True
        assert "ssn" in result.pattern_names
        assert "email" not in result.pattern_names

    def test_detect_ip_address(self) -> None:
        detector = PIIDetector()
        result = detector.scan_string("Server: 192.168.1.100")
        assert result.contains_pii is True
        assert "ip_address" in result.pattern_names

    def test_match_details(self) -> None:
        detector = PIIDetector(enabled_patterns=["email"])
        result = detector.scan_string("Email: alice@example.com")
        assert len(result.matches) == 1
        assert result.matches[0].pattern_name == "email"
        assert result.matches[0].matched_text == "alice@example.com"
