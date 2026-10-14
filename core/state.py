"""Sleep/awake state machine.

SLEEPING: only the wake word runs.
AWAKE:    record what you say, transcribe it, handle it, then keep listening
          for a follow-up. Silence or a sleep phrase sends it back to sleep.
"""
from __future__ import annotations

import logging
import random
import re
import threading
from enum import Enum
from typing import Callable

from brain.conversation import Conversation
from core.config import Settings
from voice.audio import Microphone
from voice.recorder import Recorder
from voice.stt import Transcriber
from voice.tts import Speaker
from voice.wakeword import WakeWord

log = logging.getLogger("jarvis.state")


class State(Enum):
    SLEEPING = "sleeping"
    AWAKE = "awake"
    PAUSED = "paused"


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z' ]", "", text.lower()).strip()


class Assistant:
    def __init__(
        self,
        settings: Settings,
        speaker: Speaker,
        brain: Conversation,
        on_state: Callable[[str], None] = lambda _s: None,
    ) -> None:
        self.settings = settings
        self.on_state = on_state
        self._paused = threading.Event()
        self._interrupt = threading.Event()
        self.speaker = speaker
        self.wake = WakeWord(
            model=settings.get("wake.model", "hey_jarvis"),
            threshold=float(settings.get("wake.threshold", 0.5)),
            cooldown=float(settings.get("wake.cooldown_seconds", 2)),
        )
        self.stt = Transcriber(
            model=settings.get("stt.model", "large-v3-turbo"),
            device=settings.get("stt.device", "auto"),
            language=settings.get("stt.language"),
            beam_size=int(settings.get("stt.beam_size", 1)),
        )
        self.first_listen = Recorder(
            aggressiveness=int(settings.get("listen.vad_aggressiveness", 2)),
            start_timeout=float(settings.get("listen.start_timeout_seconds", 5)),
            end_silence_ms=int(settings.get("listen.end_silence_ms", 800)),
            max_seconds=float(settings.get("listen.max_seconds", 15)),
        )
        self.followup_listen = Recorder(
            aggressiveness=int(settings.get("listen.vad_aggressiveness", 2)),
            start_timeout=float(settings.get("awake.followup_seconds", 8)),
            end_silence_ms=int(settings.get("listen.end_silence_ms", 800)),
            max_seconds=float(settings.get("listen.max_seconds", 15)),
        )
        self.acks = settings.get("wake.acknowledgements") or ["Yes?"]
        self.sleep_phrases = {_normalize(p) for p in settings.get("awake.sleep_phrases") or []}
        self.brain = brain
        self.state = State.SLEEPING

    def _set(self, state: State) -> None:
        if state != self.state:
            log.info("state: %s -> %s", self.state.value, state.value)
            self.state = state
            self.on_state(state.value)

    # ── controls, safe to call from the UI thread ────────────────────────────
    def pause(self) -> None:
        self._paused.set()
        self.interrupt()

    def resume(self) -> None:
        self._paused.clear()

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def interrupt(self) -> None:
        """Kill switch: stop talking, drop any pending action, go back to sleep."""
        self._interrupt.set()
        self.speaker.stop()
        self.brain.cancel_pending()

    def _say(self, mic: Microphone, text: str) -> None:
        if self._interrupt.is_set():
            return
        self.speaker.say(text)
        mic.flush()  # don't hear ourselves

    def handle(self, text: str) -> str | None:
        """Turn what was heard into a spoken reply."""
        return self.brain.reply(text)

    def _conversation(self, mic: Microphone) -> None:
        self._interrupt.clear()
        self._set(State.AWAKE)
        self._say(mic, random.choice(self.acks))
        recorder = self.first_listen
        stop = self._interrupt.is_set

        while not stop():
            audio = recorder.record(mic, should_stop=stop)
            if audio is None or stop():
                break
            text = self.stt.transcribe(audio)
            if not text:
                recorder = self.followup_listen
                continue
            if _normalize(text) in self.sleep_phrases:
                self._say(mic, "Going to sleep.")
                break
            reply = self.handle(text)
            if reply:
                self._say(mic, reply)
            recorder = self.followup_listen

        if stop():
            log.info("interrupted")
        mic.flush()
        self.wake.reset()
        self._set(State.PAUSED if self.paused else State.SLEEPING)

    def run(self) -> None:
        log.info("listening for the wake word")
        self.on_state(self.state.value)
        with Microphone() as mic:
            while True:
                frame = mic.read()  # keep draining the mic even while paused
                if self.paused:
                    self._set(State.PAUSED)
                    continue
                if self.state is State.PAUSED:
                    self.wake.reset()
                    self._set(State.SLEEPING)
                if self.wake.detect(frame):
                    self._conversation(mic)
