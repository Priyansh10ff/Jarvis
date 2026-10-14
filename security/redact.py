"""Scrub secrets from text before it is logged or sent to a cloud model."""
from __future__ import annotations

import logging
import re

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)),
    ("anthropic_key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("openai_key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{20,}")),
    ("groq_key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")),
    ("aws_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("google_key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("password", re.compile(r"(?i)\b(pass(?:word|code)?|pwd|pin)\b(\s*(?:is|:|=)\s*)(\S+)")),
    ("otp", re.compile(r"(?i)\b(otp|verification code|one time password)\b(\s*(?:is|:|=)?\s*)(\d{4,8})\b")),
]
CARD = re.compile(r"\b\d(?:[ -]?\d){12,18}\b")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def _card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group(0))
    return "[REDACTED:card]" if 13 <= len(digits) <= 19 and _luhn_ok(digits) else match.group(0)


def redact(text: str) -> str:
    if not text:
        return text
    for kind, pattern in PATTERNS:
        if kind in ("password", "otp"):
            text = pattern.sub(lambda m, k=kind: f"{m.group(1)}{m.group(2)}[REDACTED:{k}]", text)
        else:
            text = pattern.sub(f"[REDACTED:{kind}]", text)
    return CARD.sub(_card, text)


class RedactingFilter(logging.Filter):
    """Attach to log handlers so secrets never reach log files."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        return True


def redact_value(value):
    """Redact strings inside nested dicts/lists (tool arguments)."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_value(v) for v in value]
    return value
