"""One chat() interface over Groq, Claude and local Ollama."""
from __future__ import annotations

from typing import Protocol

Message = dict[str, str]  # {"role": "user" | "assistant", "content": "..."}


class Provider(Protocol):
    name: str
    model: str

    def chat(self, system: str, messages: list[Message], max_tokens: int) -> str: ...


class OpenAICompatible:
    """Groq and Ollama both expose an OpenAI-compatible endpoint."""

    def __init__(self, name: str, model: str, base_url: str, api_key: str, timeout: float) -> None:
        from openai import OpenAI

        self.name = name
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    def chat(self, system: str, messages: list[Message], max_tokens: int) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, *messages],
            max_tokens=max_tokens,
            temperature=0.6,
        )
        return (resp.choices[0].message.content or "").strip()


class Claude:
    def __init__(self, model: str, api_key: str, timeout: float) -> None:
        from anthropic import Anthropic

        self.name = "claude"
        self.model = model
        self._client = Anthropic(api_key=api_key, timeout=timeout, max_retries=0)

    def chat(self, system: str, messages: list[Message], max_tokens: int) -> str:
        resp = self._client.messages.create(
            model=self.model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        return "".join(b.text for b in resp.content if b.type == "text").strip()
