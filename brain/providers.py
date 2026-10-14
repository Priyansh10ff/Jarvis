"""One interface over Groq, Claude and local Ollama, with a tool-calling loop.

run() keeps each provider's native message format inside the loop and returns
only the final text; the shared history stays plain user/assistant text.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Protocol

from tools.registry import Tool

log = logging.getLogger("jarvis.brain")

Message = dict[str, str]  # {"role": "user" | "assistant", "content": "..."}
Execute = Callable[[str, dict[str, Any]], str]


class Provider(Protocol):
    name: str
    model: str

    def run(
        self, system: str, messages: list[Message], tools: list[Tool], execute: Execute,
        max_tokens: int, max_steps: int,
    ) -> str: ...


class OpenAICompatible:
    """Groq and Ollama both expose an OpenAI-compatible endpoint."""

    def __init__(self, name: str, model: str, base_url: str, api_key: str, timeout: float) -> None:
        from openai import OpenAI

        self.name = name
        self.model = model
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    def run(self, system, messages, tools, execute, max_tokens, max_steps) -> str:
        convo: list[dict[str, Any]] = [{"role": "system", "content": system}, *messages]
        schemas = [t.openai_schema() for t in tools] or None

        for _ in range(max_steps):
            resp = self._client.chat.completions.create(
                model=self.model, messages=convo, tools=schemas,
                max_tokens=max_tokens, temperature=0.4,
            )
            msg = resp.choices[0].message
            calls = msg.tool_calls or []
            if not calls:
                return (msg.content or "").strip()

            convo.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in calls
                ],
            })
            for c in calls:
                try:
                    args = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                convo.append({"role": "tool", "tool_call_id": c.id, "content": execute(c.function.name, args)})
        return "Done."


class Claude:
    def __init__(self, model: str, api_key: str, timeout: float) -> None:
        from anthropic import Anthropic

        self.name = "claude"
        self.model = model
        self._client = Anthropic(api_key=api_key, timeout=timeout, max_retries=0)

    def run(self, system, messages, tools, execute, max_tokens, max_steps) -> str:
        convo: list[dict[str, Any]] = list(messages)
        schemas = [t.anthropic_schema() for t in tools]

        for _ in range(max_steps):
            kwargs: dict[str, Any] = dict(model=self.model, system=system, messages=convo, max_tokens=max_tokens)
            if schemas:
                kwargs["tools"] = schemas
            resp = self._client.messages.create(**kwargs)
            uses = [b for b in resp.content if b.type == "tool_use"]
            if not uses:
                return "".join(b.text for b in resp.content if b.type == "text").strip()

            convo.append({"role": "assistant", "content": resp.content})
            convo.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": u.id, "content": execute(u.name, dict(u.input or {}))}
                    for u in uses
                ],
            })
        return "Done."
