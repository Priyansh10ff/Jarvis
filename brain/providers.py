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

PENDING = "Not run yet"


def fast_reply(results: list[str]) -> str | None:
    """If every action succeeded, speak the tool results directly and skip a second
    model round trip (halves the delay for 'open X', 'volume down', ...).
    Errors and blocks go back to the model so it can explain."""
    if not results:
        return None
    if any(r.startswith(("Error", "Blocked")) for r in results):
        return None
    if any(r.startswith(PENDING) for r in results):
        return "Confirm?"  # the conversation replaces this with the real question
    return ". ".join(r.rstrip(".") for r in results) + "."


class Provider(Protocol):
    name: str
    model: str

    def run(
        self, system: str, messages: list[Message], tools: list[Tool], execute: Execute,
        max_tokens: int, max_steps: int, finals: set[str] = ...,
    ) -> str: ...


class OpenAICompatible:
    """Groq and Ollama both expose an OpenAI-compatible endpoint."""

    def __init__(
        self, name: str, model: str, base_url: str, api_key: str, timeout: float,
        fast: bool = True, reasoning_effort: str | None = "low",
    ) -> None:
        from openai import OpenAI

        self.name = name
        self.model = model
        self.fast = fast
        self.reasoning_effort = reasoning_effort
        self._client = OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    def _extra(self) -> dict[str, Any]:
        # gpt-oss models think before answering; "low" keeps that short for speed.
        if self.reasoning_effort and "gpt-oss" in self.model:
            return {"reasoning_effort": self.reasoning_effort}
        return {}

    FALLBACK_MODELS = (
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "llama-3.1-8b-instant",
    )

    def _pick_available_model(self) -> bool:
        """Configured model missing or blocked: switch to one this key can use."""
        try:
            ids = {m.id for m in self._client.models.list().data}
        except Exception:
            return False
        for candidate in self.FALLBACK_MODELS:
            if candidate in ids and candidate != self.model:
                log.warning("%s: model %s unavailable, using %s instead", self.name, self.model, candidate)
                self.model = candidate
                return True
        log.error("%s: none of %s available; models on this key: %s", self.name, self.FALLBACK_MODELS, sorted(ids))
        return False

    def run(self, system, messages, tools, execute, max_tokens, max_steps, finals=frozenset()) -> str:
        from openai import NotFoundError

        try:
            return self._run(system, messages, tools, execute, max_tokens, max_steps, finals)
        except NotFoundError:
            if self._pick_available_model():
                return self._run(system, messages, tools, execute, max_tokens, max_steps, finals)
            raise

    def _run(self, system, messages, tools, execute, max_tokens, max_steps, finals=frozenset()) -> str:
        convo: list[dict[str, Any]] = [{"role": "system", "content": system}, *messages]
        schemas = [t.openai_schema() for t in tools] or None

        for _ in range(max_steps):
            resp = self._client.chat.completions.create(
                model=self.model, messages=convo, tools=schemas,
                max_tokens=max_tokens, temperature=0.4, extra_body=self._extra() or None,
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
            results = []
            for c in calls:
                try:
                    args = json.loads(c.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = execute(c.function.name, args)
                results.append(result)
                convo.append({"role": "tool", "tool_call_id": c.id, "content": result})
            all_final = all(c.function.name in finals for c in calls)
            quick = fast_reply(results) if self.fast and all_final else None
            if quick:
                return quick
        return "I ran out of steps before finishing. Tell me what to do next."


class Claude:
    def __init__(self, model: str, api_key: str, timeout: float, fast: bool = True, smart_model: str | None = None) -> None:
        from anthropic import Anthropic

        self.name = "claude"
        self.fast_model = model
        self.smart_model = smart_model or model
        self.model = model
        self.fast = fast
        self.smart = False  # set per request by the router
        self._client = Anthropic(api_key=api_key, timeout=timeout, max_retries=1)

    def run(self, system, messages, tools, execute, max_tokens, max_steps, finals=frozenset()) -> str:
        self.model = self.smart_model if self.smart else self.fast_model
        convo: list[dict[str, Any]] = list(messages)
        schemas = [t.anthropic_schema() for t in tools]
        if schemas:
            # Cache the (large, unchanging) tool list and system prompt: faster and much cheaper.
            schemas[-1] = {**schemas[-1], "cache_control": {"type": "ephemeral"}}
        system_blocks = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

        for _ in range(max_steps):
            kwargs: dict[str, Any] = dict(model=self.model, system=system_blocks, messages=convo, max_tokens=max_tokens)
            if schemas:
                kwargs["tools"] = schemas
            resp = self._client.messages.create(**kwargs)
            uses = [b for b in resp.content if b.type == "tool_use"]
            if not uses:
                return "".join(b.text for b in resp.content if b.type == "text").strip()

            results = [execute(u.name, dict(u.input or {})) for u in uses]
            convo.append({"role": "assistant", "content": resp.content})
            convo.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": u.id, "content": r} for u, r in zip(uses, results)
                ],
            })
            all_final = all(u.name in finals for u in uses)
            quick = fast_reply(results) if self.fast and all_final else None
            if quick:
                return quick
        return "I ran out of steps before finishing. Tell me what to do next."
