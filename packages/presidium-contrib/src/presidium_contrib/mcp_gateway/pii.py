"""PII detection in tool results via regex patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_DEFAULT_PATTERNS: dict[str, re.Pattern[str]] = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "credit_card": re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "phone_us": re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ip_address": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
}

_MASK = "***"


@dataclass(frozen=True)
class PIIMatch:
    pattern_name: str
    matched_text: str
    start: int
    end: int


@dataclass
class PIIResult:
    contains_pii: bool
    matches: list[PIIMatch] = field(default_factory=list)
    pattern_names: list[str] = field(default_factory=list)


class PIIDetector:
    def __init__(
        self,
        *,
        patterns: dict[str, re.Pattern[str]] | None = None,
        enabled_patterns: list[str] | None = None,
    ) -> None:
        base = patterns or dict(_DEFAULT_PATTERNS)
        if enabled_patterns is not None:
            self._patterns = {k: v for k, v in base.items() if k in enabled_patterns}
        else:
            self._patterns = base

    def scan_string(self, text: str) -> PIIResult:
        matches: list[PIIMatch] = []
        pattern_names: set[str] = set()

        for name, pattern in self._patterns.items():
            for m in pattern.finditer(text):
                matches.append(
                    PIIMatch(
                        pattern_name=name,
                        matched_text=m.group(),
                        start=m.start(),
                        end=m.end(),
                    )
                )
                pattern_names.add(name)

        return PIIResult(
            contains_pii=len(matches) > 0,
            matches=matches,
            pattern_names=sorted(pattern_names),
        )

    def scan_dict(self, data: dict[str, Any]) -> PIIResult:
        all_matches: list[PIIMatch] = []
        all_patterns: set[str] = set()

        for value in _extract_strings(data):
            result = self.scan_string(value)
            all_matches.extend(result.matches)
            all_patterns.update(result.pattern_names)

        return PIIResult(
            contains_pii=len(all_matches) > 0,
            matches=all_matches,
            pattern_names=sorted(all_patterns),
        )

    def mask_string(self, text: str) -> str:
        result = text
        for pattern in self._patterns.values():
            result = pattern.sub(_MASK, result)
        return result

    def mask_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        masked: dict[str, Any] = {}
        for key, value in data.items():
            if isinstance(value, str):
                masked[key] = self.mask_string(value)
            elif isinstance(value, dict):
                masked[key] = self.mask_dict(value)
            elif isinstance(value, list):
                masked[key] = [
                    self.mask_dict(item)
                    if isinstance(item, dict)
                    else self.mask_string(item)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]
            else:
                masked[key] = value
        return masked


def _extract_strings(data: Any) -> list[str]:  # noqa: ANN401
    strings: list[str] = []
    if isinstance(data, str):
        strings.append(data)
    elif isinstance(data, dict):
        for v in data.values():
            strings.extend(_extract_strings(v))
    elif isinstance(data, list):
        for item in data:
            strings.extend(_extract_strings(item))
    return strings
