"""Pick a model per request: preferred one first, then fall back in order."""
from __future__ import annotations

import logging
import time

from brain.providers import Claude, Message, OpenAICompatible, Provider
from core.config import Settings
from core.secrets import get_secret

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
        self.providers: dict[str, Provider] = {}
        for name in self.order:
            provider = _build(name, settings)
            if provider:
                self.providers[name] = provider
            else:
                log.info("provider %s unavailable (no key or model)", name)
        self.preferred: str | None = None

    def available(self) -> list[str]:
        return list(self.providers)

    def prefer(self, name: str | None) -> None:
        self.preferred = name

    def chat(self, system: str, messages: list[Message]) -> tuple[str, str]:
        """Return (reply, provider name). Raises NoModelAvailable if all fail."""
        names = [n for n in self.order if n in self.providers]
        if self.preferred in names:
            names.remove(self.preferred)
            names.insert(0, self.preferred)

        for name in names:
            provider = self.providers[name]
            t0 = time.monotonic()
            try:
                reply = provider.chat(system, messages, self.max_tokens)
            except Exception as e:
                log.warning("%s failed: %s", name, e)
                continue
            log.info("%s/%s replied in %.0f ms", name, provider.model, (time.monotonic() - t0) * 1000)
            if reply:
                return reply, name
        raise NoModelAvailable("No model answered")
