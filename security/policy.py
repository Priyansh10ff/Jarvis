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


# App control: tools that touch whatever window they're aimed at.
WINDOW_TOOLS = {"focus_window", "window_action", "type_text", "press_keys", "click_element", "read_window"}
RISKY_CLICKS = re.compile(
    r"(?i)\b(send|delete|remove|pay|buy|purchase|order|checkout|submit|post|publish|confirm|transfer|"
    r"uninstall|format|erase|sign out|log ?out|reset|discard|unsubscribe)\b"
)
MESSAGING_APPS = re.compile(
    r"(?i)(whatsapp|telegram|discord|slack|teams|messenger|signal|instagram|claude|chatgpt|gmail|outlook|"
    r"mail|linkedin|twitter|\bx\b|skype|zoom)"
)
DEFAULT_PRIVATE_WINDOWS = ["bitwarden", "1password", "keepass", "lastpass", "dashlane", "credential",
                           "windows security", "password", "authenticator"]


@dataclass(frozen=True)
class Decision:
    action: str  # allow | confirm | deny
    reason: str = ""


class Policy:
    def __init__(self, settings: Settings) -> None:
        self.overrides: dict[str, str] = dict(settings.get("security.levels") or {})
        self.blocked_domains = [d.lower().lstrip(".") for d in settings.get("security.blocked_domains") or []]
        self.rate = int(settings.get("security.max_tool_calls_per_minute", 20))
        self.private_windows = [w.lower() for w in (settings.get("security.private_windows") or DEFAULT_PRIVATE_WINDOWS)]
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

    def _check_window_tool(self, name: str, args: dict[str, Any]) -> Decision | None:
        try:
            from tools.uia import target_title

            title = target_title(args.get("window")).lower()
        except Exception:
            title = ""
        if any(p in title for p in self.private_windows):
            return Decision("deny", "that window is private (password manager or security)")
        if name == "click_element" and RISKY_CLICKS.search(str(args.get("name", ""))):
            return Decision("confirm")
        if name == "press_keys" and "enter" in str(args.get("keys", "")).lower() and MESSAGING_APPS.search(title):
            return Decision("confirm")  # Enter in a chat or mail app sends a message
        return None

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

        if name in WINDOW_TOOLS:
            decision = self._check_window_tool(name, args)
            if decision:
                return decision

        level = self._level(name)
        if level == "deny":
            return Decision("deny", f"{name} is turned off in settings")
        if level == "confirm":
            return Decision("confirm")
        return Decision("allow")
