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
        self.wake_mode = settings.get("wake.mode", "phrase")  # phrase | model
        self.wake_words = {_normalize(w) for w in settings.get("wake.phrases") or ["hey"]}
        self.wake = None
        if self.wake_mode == "model":
            self.wake = WakeWord(
                model=settings.get("wake.model", "hey_jarvis"),
                threshold=float(settings.get("wake.threshold", 0.5)),
                cooldown=float(settings.get("wake.cooldown_seconds", 2)),
            )
        self.wake_listen = Recorder(
            aggressiveness=int(settings.get("listen.vad_aggressiveness", 2)),
            start_timeout=30,
            end_silence_ms=int(settings.get("listen.end_silence_ms", 800)),
            max_seconds=float(settings.get("listen.max_seconds", 15)),
        )
        self.stt: Transcriber | None = None
        self._stt_ready = threading.Event()
        self._load_stt()  # load fully before going live (no lag on the first command)
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
        log.info("loading speech model")
        try:
            self.stt = Transcriber(
                model=s.get("stt.model", "large-v3-turbo"),
                device=s.get("stt.device", "auto"),
                language=s.get("stt.language"),
                beam_size=int(s.get("stt.beam_size", 1)),
            )
            self.stt.warm_up()
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

    def _reset_wake(self) -> None:
        if self.wake:
            self.wake.reset()

    def _split_wake(self, text: str) -> tuple[bool, str]:
        """'Hey, open Spotify' -> (True, 'open Spotify'); 'hello there' -> (False, '')."""
        words = text.strip().split()
        if not words:
            return False, ""
        if _normalize(words[0]) in self.wake_words:
            rest_words = words[1:]
            if rest_words and _normalize(rest_words[0]) == _normalize(self.settings.assistant_name):
                rest_words = rest_words[1:]  # "hey jarvis ..." also works
            rest = " ".join(rest_words).lstrip(",.!? ").strip()
            return True, rest
        return False, ""

    def _conversation(self, mic: Microphone, first_text: str = "") -> None:
        self._interrupt.clear()
        if not self._stt_ready.is_set():
            log.info("woke before the speech model was ready")
            self._say(mic, "I'm still loading my speech model. Use the typing bar for now.")
            self._reset_wake()
            return
        self._set(State.AWAKE)
        if not first_text:
            self._say(mic, random.choice(self.acks))
        recorder = self.first_listen
        stop = self._interrupt.is_set
        pending_text = first_text

        while not stop():
            if pending_text:
                text, pending_text = pending_text, ""
            else:
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
            self.on_event("activity", "thinking")
            reply = self.handle(text)
            if reply:
                self.on_event("reply", reply)
                self._say(mic, reply)
            recorder = self.followup_listen

        if stop():
            log.info("interrupted")
        mic.flush()
        self._reset_wake()
        self._set(State.PAUSED if self.paused else State.SLEEPING)

    def _check_pause(self) -> bool:
        """True while paused. Handles the paused -> sleeping transition."""
        if self.paused:
            self._set(State.PAUSED)
            return True
        if self.state is State.PAUSED:
            self._reset_wake()
            self._set(State.SLEEPING)
        return False

    def run(self) -> None:
        mic_device = self.settings.get("audio.input_device")
        gain = float(self.settings.get("audio.gain", 1.0))
        self.on_state(self.state.value)
        with Microphone(device=mic_device, gain=gain) as mic:
            if self.wake_mode == "model":
                self._run_model(mic)
            else:
                self._run_phrase(mic)

    def _run_phrase(self, mic: Microphone) -> None:
        """Wake on a spoken phrase ("hey"): every utterance is transcribed locally and
        checked for the wake word at the start. Nothing leaves the PC at this stage."""
        log.info("listening for: %s", ", ".join(sorted(self.wake_words)))
        while True:
            if self._check_pause():
                mic.read()
                continue
            if not self._stt_ready.is_set():
                mic.read()
                continue
            audio = self.wake_listen.record(mic, should_stop=lambda: self.paused)
            if audio is None:
                continue
            text = self.stt.transcribe(audio)  # type: ignore[union-attr]
            woke, rest = self._split_wake(text)
            if woke:
                log.info("wake phrase heard%s", f", with command: {rest}" if rest else "")
                self._conversation(mic, first_text=rest)

    def _run_model(self, mic: Microphone) -> None:
        log.info("listening for the wake word model")
        near_miss = 0.0
        while True:
            frame = mic.read()  # keep draining the mic even while paused
            if self._check_pause():
                continue
            if self.wake.detect(frame):  # type: ignore[union-attr]
                near_miss = 0.0
                self._conversation(mic)
            elif self.wake.last_score > max(0.15, near_miss):  # type: ignore[union-attr]
                near_miss = self.wake.last_score  # type: ignore[union-attr]
                log.info("heard something close to the wake word (score %.2f, needs %.2f)",
                         near_miss, self.wake.threshold)  # type: ignore[union-attr]
            elif self.wake.last_score < 0.05:  # type: ignore[union-attr]
                near_miss = 0.0
