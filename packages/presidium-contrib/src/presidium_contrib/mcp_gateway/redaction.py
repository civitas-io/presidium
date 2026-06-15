"""Credential redaction for tool call parameters before audit logging."""

from __future__ import annotations

import re
from typing import Any

_CREDENTIAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(api[_\-]?key|token|secret|password|credential)\s*[:=]\s*\S+"),
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"(?i)basic\s+[A-Za-z0-9+/=]{10,}"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"gho_[a-zA-Z0-9]{36}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]

_REDACTED = "**REDACTED**"

_SENSITIVE_KEY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)(api[_\-]?key|token|secret|password|credential|auth)"),
]


def redact_string(value: str) -> str:
    result = value
    for pattern in _CREDENTIAL_PATTERNS:
        result = pattern.sub(_REDACTED, result)
    return result


def redact_dict(data: dict[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, value in data.items():
        if any(p.search(key) for p in _SENSITIVE_KEY_PATTERNS):
            redacted[key] = _REDACTED
        elif isinstance(value, str):
            redacted[key] = redact_string(value)
        elif isinstance(value, dict):
            redacted[key] = redact_dict(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_dict(item)
                if isinstance(item, dict)
                else redact_string(item)
                if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            redacted[key] = value
    return redacted
