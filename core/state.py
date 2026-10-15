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
from typing import Any, Callable

import numpy as np

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
        on_event: Callable[[str, Any], None] = lambda _k, _v: None,
    ) -> None:
        self.settings = settings
        self.on_state = on_state
        self.on_event = on_event  # ("activity", listening|thinking|speaking), ("level", 0-1), ("heard"|"reply", text)
        self._paused = threading.Event()
        self._interrupt = threading.Event()
        self.speaker = speaker
        self.wake = WakeWord(
            model=settings.get("wake.model", "hey_jarvis"),
            threshold=float(settings.get("wake.threshold", 0.5)),
            cooldown=float(settings.get("wake.cooldown_seconds", 2)),
        )
        self.stt: Transcriber | None = None
        self._stt_ready = threading.Event()
        threading.Thread(target=self._load_stt, name="stt-load", daemon=True).start()
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

    def _load_stt(self) -> None:
        s = self.settings
        log.info("loading speech model (first run downloads ~1.6 GB)")
        try:
            self.stt = Transcriber(
                model=s.get("stt.model", "large-v3-turbo"),
                device=s.get("stt.device", "auto"),
                language=s.get("stt.language"),
                beam_size=int(s.get("stt.beam_size", 1)),
            )
            self._stt_ready.set()
        except Exception:
            log.exception("speech model failed to load")

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
        self.on_event("activity", "speaking")
        self.speaker.say(text)
        mic.flush()  # don't hear ourselves
        self.on_event("activity", "listening")

    def _mic_level(self, frame: np.ndarray) -> None:
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        self.on_event("level", min(1.0, rms / 3000.0))

    def handle(self, text: str) -> str | None:
        """Turn what was heard into a spoken reply."""
        return self.brain.reply(text)

    def _conversation(self, mic: Microphone) -> None:
        self._interrupt.clear()
        if not self._stt_ready.is_set():
            log.info("woke before the speech model was ready")
            self._say(mic, "I'm still loading my speech model. Use the typing bar for now.")
            self.wake.reset()
            return
        self._set(State.AWAKE)
        self._say(mic, random.choice(self.acks))
        recorder = self.first_listen
        stop = self._interrupt.is_set

        while not stop():
            audio = recorder.record(mic, should_stop=stop, on_frame=self._mic_level)
            if audio is None or stop():
                break
            self.on_event("activity", "thinking")
            text = self.stt.transcribe(audio)  # type: ignore[union-attr]
            if not text:
                self.on_event("activity", "listening")
                recorder = self.followup_listen
                continue
            self.on_event("heard", text)
            if _normalize(text) in self.sleep_phrases:
                self._say(mic, "Going to sleep.")
                break
            reply = self.handle(text)
            if reply:
                self.on_event("reply", reply)
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
        mic_device = self.settings.get("audio.input_device")
        gain = float(self.settings.get("audio.gain", 1.0))
        near_miss = 0.0
        with Microphone(device=mic_device, gain=gain) as mic:
            while True:
                frame = mic.read()  # keep draining the mic even while paused
                if self.paused:
                    self._set(State.PAUSED)
                    continue
                if self.state is State.PAUSED:
                    self.wake.reset()
                    self._set(State.SLEEPING)
                if self.wake.detect(frame):
                    near_miss = 0.0
                    self._conversation(mic)
                elif self.wake.last_score > max(0.15, near_miss):
                    near_miss = self.wake.last_score
                    log.info("heard something close to the wake word (score %.2f, needs %.2f)",
                             near_miss, self.wake.threshold)
                elif self.wake.last_score < 0.05:
                    near_miss = 0.0
