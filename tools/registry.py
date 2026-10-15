"""Tool registry: each tool has a JSON schema, a function and a permission level.

Levels:
    free     runs immediately
    confirm  Jarvis asks "say yes to confirm" first; the code enforces it, not the model
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("jarvis.tools")


@dataclass
class Tool:
    name: str
    description: str
    func: Callable[..., str]
    parameters: dict[str, Any] = field(default_factory=lambda: {"type": "object", "properties": {}})
    level: str = "free"
    confirm_prompt: str | None = None  # what to ask before a confirm-level tool runs
    final: bool = True  # result can be spoken as-is (no second model call needed)

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }

    def anthropic_schema(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "input_schema": self.parameters}


REGISTRY: dict[str, Tool] = {}


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any] | None = None,
    level: str = "free",
    confirm_prompt: str | None = None,
    final: bool = True,
) -> Callable[[Callable[..., str]], Callable[..., str]]:
    def wrap(func: Callable[..., str]) -> Callable[..., str]:
        REGISTRY[name] = Tool(
            name=name,
            description=description,
            func=func,
            parameters=parameters or {"type": "object", "properties": {}},
            level=level,
            confirm_prompt=confirm_prompt,
            final=final,
        )
        return func

    return wrap


def run_tool(name: str, args: dict[str, Any]) -> str:
    tool_ = REGISTRY.get(name)
    if not tool_:
        return f"Error: unknown tool {name}"
    try:
        result = tool_.func(**args)
    except TypeError as e:
        result = f"Error: bad arguments for {name}: {e}"
    except Exception as e:
        log.exception("tool %s failed", name)
        result = f"Error: {name} failed: {e}"
    log.info("tool %s(%s) -> %s", name, args, result)
    return result
