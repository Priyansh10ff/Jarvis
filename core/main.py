"""Entry point: python -m core.main"""
from __future__ import annotations

import logging
import sys
import time

from core import single_instance
from core.config import ROOT, load_settings
from core.greeting import build_greeting
from core.secrets import KNOWN, has_secret

log = logging.getLogger("jarvis")


def setup_logging(level: str, file: str) -> None:
    log_path = ROOT / file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(log_path, encoding="utf-8")]
    if sys.stderr is not None:  # pythonw has no console
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def main(startup: bool = False) -> None:
    settings = load_settings()
    setup_logging(settings.get("logging.level", "INFO"), settings.get("logging.file", "logs/jarvis.log"))

    if not single_instance.acquire():
        log.info("Another instance is already running, exiting.")
        return

    if startup:
        time.sleep(float(settings.get("startup.delay_seconds", 0)))

    for name in KNOWN:
        log.info("key %-10s %s", name, "ok" if has_secret(name) else "missing")

    if settings.get("startup.greet", True):
        text = build_greeting(settings.user_name, settings.assistant_name)
        try:
            from voice.tts import Speaker

            Speaker(rate=int(settings.get("voice.tts_rate", 175))).say(text)
        except Exception:
            log.exception("Greeting failed; text was: %s", text)

    log.info("%s core online for %s", settings.assistant_name, settings.user_name)


if __name__ == "__main__":
    main()
