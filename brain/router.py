"""Pick a model per request: preferred one first, then fall back in order."""
from __future__ import annotations

import logging
import time
from typing import Any

from brain.providers import Claude, Execute, Message, OpenAICompatible, Provider
from core.config import Settings
from core.secrets import get_secret
from security.redact import redact
from tools.registry import Tool

log = logging.getLogger("jarvis.brain")

GROQ_URL = "https://api.groq.com/openai/v1"


class NoModelAvailable(RuntimeError):
    pass


def _build(name: str, settings: Settings) -> Provider | None:
    cfg = settings.get(f"brain.providers.{name}", {}) or {}
    timeout = float(settings.get("brain.timeout_seconds", 20))
    model = cfg.get("model")
    if not model:
        return None
    if name == "groq":
        key = get_secret("groq")
        return OpenAICompatible("groq", model, GROQ_URL, key, timeout) if key else None
    if name == "claude":
        key = get_secret("anthropic")
        return Claude(model, key, timeout) if key else None
    if name == "local":
        url = cfg.get("base_url", "http://localhost:11434/v1")
        return OpenAICompatible("local", model, url, "ollama", timeout)
    return None


class Router:
    def __init__(self, settings: Settings) -> None:
        self.order: list[str] = list(settings.get("brain.order") or ["groq", "claude", "local"])
        self.max_tokens = int(settings.get("brain.max_tokens", 300))
        self.max_steps = int(settings.get("brain.max_tool_steps", 5))
        self.providers: dict[str, Provider] = {}
        for name in self.order:
            provider = _build(name, settings)
            if provider:
                self.providers[name] = provider
            else:
                log.info("provider %s unavailable (no key or model)", name)
        self.preferred: str | None = None
        self.redact_cloud = bool(settings.get("security.redact_cloud", True))

    def available(self) -> list[str]:
        return list(self.providers)

    def prefer(self, name: str | None) -> None:
        self.preferred = name

    def run(self, system: str, messages: list[Message], tools: list[Tool], execute: Execute) -> tuple[str, str]:
        """Return (reply, provider name). Raises NoModelAvailable if all fail."""
        names = [n for n in self.order if n in self.providers]
        if self.preferred in names:
            names.remove(self.preferred)
            names.insert(0, self.preferred)

        for name in names:
            provider = self.providers[name]
            calls = 0

            def counted(tool_name: str, args: dict[str, Any]) -> str:
                nonlocal calls
                calls += 1
                return execute(tool_name, args)

            outbound = messages
            if name != "local" and self.redact_cloud:  # nothing secret leaves the PC
                outbound = [{**m, "content": redact(m["content"])} for m in messages]

            t0 = time.monotonic()
            try:
                reply = provider.run(system, outbound, tools, counted, self.max_tokens, self.max_steps)
            except Exception as e:
                log.warning("%s failed: %s", name, e)
                if calls:  # never repeat actions on another model
                    return "Done, but I lost the connection before I could confirm.", name
                continue
            log.info("%s/%s replied in %.0f ms (%d tool calls)", name, provider.model, (time.monotonic() - t0) * 1000, calls)
            return reply or "Done.", name
        raise NoModelAvailable("No model answered")
