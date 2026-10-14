"""Conversation: system prompt, short history, model switching, speech-friendly replies."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime

from brain.providers import Message
from brain.router import NoModelAvailable, Router
from core.config import Settings

log = logging.getLogger("jarvis.brain")

PROVIDER_WORDS = {
    "claude": "claude",
    "groq": "groq",
    "grok": "groq",   # common mishearing
    "local": "local",
    "ollama": "local",
    "offline": "local",
}
SWITCH = re.compile(r"^(?:please\s+)?(?:use|switch to|change to)\s+(?:the\s+)?(\w+)(?:\s+model)?[.!]?$", re.I)


def _system_prompt(settings: Settings) -> str:
    now = datetime.now().strftime("%A %d %B %Y, %I:%M %p")
    return (
        f"You are {settings.assistant_name}, a personal voice assistant running on "
        f"{settings.user_name}'s Windows PC. It is {now}.\n"
        "Your replies are spoken aloud, so:\n"
        "- Answer in one to three short sentences unless asked for detail.\n"
        "- No markdown, lists, code blocks, emojis or URLs.\n"
        "- Reply in the language the user speaks (English or Hinglish).\n"
        "You cannot control the computer yet. If asked to open apps, files or websites, "
        "say that ability is coming soon instead of pretending you did it."
    )


def speakable(text: str) -> str:
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"[*_`#>]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


class Conversation:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.router = Router(settings)
        self.max_turns = int(settings.get("brain.history_turns", 10))
        self.reset_after = float(settings.get("brain.history_reset_minutes", 10)) * 60
        self.history: list[Message] = []
        self._last = 0.0
        log.info("models available: %s", ", ".join(self.router.available()) or "none")

    def _switch(self, text: str) -> str | None:
        match = SWITCH.match(text.strip())
        if not match:
            return None
        target = PROVIDER_WORDS.get(match.group(1).lower())
        if not target:
            return None
        if target not in self.router.available():
            return f"{target.capitalize()} isn't set up yet."
        self.router.prefer(target)
        return f"Switched to {'the local model' if target == 'local' else target.capitalize()}."

    def reply(self, text: str) -> str:
        switched = self._switch(text)
        if switched:
            return switched

        now = time.monotonic()
        if now - self._last > self.reset_after:
            self.history = []
        self._last = now

        self.history.append({"role": "user", "content": text})
        try:
            answer, _ = self.router.chat(_system_prompt(self.settings), self.history)
        except NoModelAvailable:
            self.history.pop()
            return "I can't reach any AI model right now. Add an API key or start Ollama."

        answer = speakable(answer)
        self.history.append({"role": "assistant", "content": answer})
        self.history = self.history[-2 * self.max_turns :]
        return answer


def _cli() -> None:
    """Type to test the brain without voice: python -m brain.conversation"""
    import logging as _l

    from core.config import load_settings

    _l.basicConfig(level=_l.INFO, format="%(name)s: %(message)s")
    convo = Conversation(load_settings())
    print("Type a message (empty line to quit).")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            break
        print("jarvis>", convo.reply(text))


if __name__ == "__main__":
    _cli()
