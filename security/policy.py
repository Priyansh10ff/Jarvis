"""The policy every tool call goes through. The model proposes; this code decides.

Decisions:
    allow    run now
    confirm  ask the user to say yes first
    deny     never run

Rules the settings file cannot loosen live in this file (HARD_DENY, sensitive paths).
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass
from typing import Any

from core.config import Settings
from tools.registry import REGISTRY

log = logging.getLogger("jarvis.security")

RANK = {"free": 0, "confirm": 1, "deny": 2}

# Anything that touches these is refused, whatever the model or settings say.
SENSITIVE_PATHS = re.compile(
    r"(?i)("
    r"\.ssh[\\/]|id_rsa|id_ed25519|"
    r"login data|cookies\b|web data|local state|"          # browser password/cookie stores
    r"\\microsoft\\credentials|\\microsoft\\protect|"     # Windows credential vault
    r"\.aws[\\/]credentials|\.git-credentials|\.env\b|"
    r"settings\.local\.yaml|security[\\/]policy\.py"         # Jarvis's own controls
    r")"
)
HARD_DENY_TOOLS: set[str] = set()  # tools that must never run, added as tools grow


@dataclass(frozen=True)
class Decision:
    action: str  # allow | confirm | deny
    reason: str = ""


class Policy:
    def __init__(self, settings: Settings) -> None:
        self.overrides: dict[str, str] = dict(settings.get("security.levels") or {})
        self.blocked_domains = [d.lower().lstrip(".") for d in settings.get("security.blocked_domains") or []]
        self.rate = int(settings.get("security.max_tool_calls_per_minute", 20))
        self._calls: deque[float] = deque()

    def _level(self, name: str) -> str:
        base = REGISTRY[name].level
        override = self.overrides.get(name)
        if override in RANK and RANK[override] > RANK[base]:
            return override  # settings may only make a tool stricter
        return base

    def _strings(self, args: dict[str, Any]) -> list[str]:
        out: list[str] = []
        for value in args.values():
            if isinstance(value, str):
                out.append(value)
            elif isinstance(value, (list, tuple)):
                out.extend(v for v in value if isinstance(v, str))
        return out

    def _domain_blocked(self, url: str) -> bool:
        host = urllib.parse.urlparse(url if "://" in url else "https://" + url).netloc.lower().split(":")[0]
        return any(host == d or host.endswith("." + d) for d in self.blocked_domains)

    def check(self, name: str, args: dict[str, Any]) -> Decision:
        if name not in REGISTRY:
            return Decision("deny", f"unknown tool {name}")
        if name in HARD_DENY_TOOLS:
            return Decision("deny", f"{name} is disabled")

        now = time.monotonic()
        while self._calls and now - self._calls[0] > 60:
            self._calls.popleft()
        if len(self._calls) >= self.rate:
            return Decision("deny", "too many actions in a minute")
        self._calls.append(now)

        for text in self._strings(args):
            if SENSITIVE_PATHS.search(text):
                return Decision("deny", "touches credentials or Jarvis's own security files")

        if name == "open_website" and self._domain_blocked(str(args.get("url", ""))):
            return Decision("deny", "that site is on the blocked list")

        level = self._level(name)
        if level == "deny":
            return Decision("deny", f"{name} is turned off in settings")
        if level == "confirm":
            return Decision("confirm")
        return Decision("allow")
