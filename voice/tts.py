"""Text to speech. pyttsx3 (Windows SAPI) for now; swappable for Kokoro later."""
from __future__ import annotations

import logging

log = logging.getLogger("jarvis.tts")


class Speaker:
    def __init__(self, rate: int = 175) -> None:
        import pyttsx3

        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)

    def say(self, text: str) -> None:
        log.info("say: %s", text)
        self._engine.say(text)
        self._engine.runAndWait()

    def stop(self) -> None:
        """Cut off speech (called from the UI thread by the kill switch)."""
        try:
            self._engine.stop()
        except Exception:
            log.debug("tts stop failed", exc_info=True)
