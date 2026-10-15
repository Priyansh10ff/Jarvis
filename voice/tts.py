"""Text to speech on its own thread (Windows SAPI via pyttsx3; swappable for Kokoro later).

One speech thread owns the engine, so the voice loop and the typing bar can both
talk without clashing. List installed voices:  python -m voice.tts --list
"""
from __future__ import annotations

import logging
import queue
import threading

log = logging.getLogger("jarvis.tts")

PREFERRED = {
    "female": ["heera", "zira", "hazel", "susan", "aria", "jenny"],
    "male": ["ravi", "david", "mark", "george", "guy"],
}


def _pick_voice(engine, choice: str | None):
    voices = engine.getProperty("voices") or []
    if not choice:
        return None
    choice = choice.lower()
    names = PREFERRED.get(choice, [choice])  # "female" | "male" | part of a voice name
    for wanted in names:
        for v in voices:
            if wanted in (v.name or "").lower():
                return v
    log.warning("no installed voice matches '%s'; using the default", choice)
    return None


class Speaker:
    def __init__(self, rate: int = 175, voice: str | None = None) -> None:
        self._queue: queue.Queue[tuple[str, threading.Event] | None] = queue.Queue()
        self._engine = None
        self._ready = threading.Event()
        self._error: Exception | None = None
        self.voice_name = "default"
        self._thread = threading.Thread(target=self._worker, args=(rate, voice), name="tts", daemon=True)
        self._thread.start()
        self._ready.wait(15)
        if self._error:
            raise self._error

    def _worker(self, rate: int, voice: str | None) -> None:
        try:
            try:
                import pythoncom

                pythoncom.CoInitialize()  # SAPI is COM; this thread owns it
            except ImportError:
                pass
            import pyttsx3

            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", rate)
            chosen = _pick_voice(self._engine, voice)
            if chosen:
                self._engine.setProperty("voice", chosen.id)
                self.voice_name = chosen.name
            log.info("voice: %s", self.voice_name)
        except Exception as e:
            self._error = e
            self._ready.set()
            return
        self._ready.set()

        while True:
            item = self._queue.get()
            if item is None:
                return
            text, done = item
            try:
                log.info("say: %s", text)
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception:
                log.exception("speech failed")
            finally:
                done.set()

    def say(self, text: str, wait: bool = True) -> None:
        """Speak text. wait=False returns immediately (used by the typing bar)."""
        if not text:
            return
        done = threading.Event()
        self._queue.put((text, done))
        if wait:
            # Generous cap (about 3x normal speaking time) so a stuck speech engine can't freeze Jarvis.
            if not done.wait(timeout=10 + len(text) / 5):
                log.warning("speech took too long; continuing")

    def stop(self) -> None:
        """Cut off current speech and drop anything queued (kill switch)."""
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item:
                item[1].set()
        try:
            if self._engine:
                self._engine.stop()
        except Exception:
            log.debug("tts stop failed", exc_info=True)


if __name__ == "__main__":
    import sys

    import pyttsx3

    engine = pyttsx3.init()
    for v in engine.getProperty("voices"):
        print(f"- {v.name}")
    if "--list" not in sys.argv:
        print("\nTip: set voice.voice in settings.yaml to female, male, or part of a name above.")
