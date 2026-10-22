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
import time
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


def _brief(text: str, max_sentences: int = 2, max_chars: int = 260) -> str:
    """What gets spoken: the first couple of sentences. The full reply stays on screen/in history."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    out = " ".join(parts[:max_sentences])
    if len(out) > max_chars:
        out = out[:max_chars].rsplit(" ", 1)[0] + "…"
    return out


def _verb(word: str) -> str:
    """'Opens' -> 'open', "what's" -> 'what'."""
    w = _normalize(word).replace("'", "")
    return w[:-1] if w.endswith("s") and len(w) > 3 else w


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
        # Whisper often writes a quick "hey" as "he", "a" or "hi". Those only count
        # when a command follows ("he opens spotify"), never on their own.
        self.soft_wake_words = {_normalize(w) for w in settings.get("wake.soft_phrases") or []}
        self.command_starts = {_normalize(w) for w in settings.get("wake.command_starts") or []}
        self.wake = None
        if self.wake_mode == "model":
            self.wake = WakeWord(
                model=settings.get("wake.model", "hey_jarvis"),
                threshold=float(settings.get("wake.threshold", 0.5)),
                cooldown=float(settings.get("wake.cooldown_seconds", 2)),
            )
        self.wake_listen = Recorder(
            aggressiveness=int(settings.get("listen.vad_aggressiveness", 3)),
            noise_ratio=float(settings.get("listen.noise_ratio", 2.5)),
            min_level=float(settings.get("listen.min_level", 250)),
            start_timeout=30,
            end_silence_ms=int(settings.get("listen.end_silence_ms", 800)),
            max_seconds=float(settings.get("listen.wake_max_seconds", 6)),
        )
        self.stt: Transcriber | None = None
        self._stt_ready = threading.Event()
        self._load_stt()  # load fully before going live (no lag on the first command)
        self.first_listen = Recorder(
            aggressiveness=int(settings.get("listen.vad_aggressiveness", 3)),
            noise_ratio=float(settings.get("listen.noise_ratio", 2.5)),
            min_level=float(settings.get("listen.min_level", 250)),
            start_timeout=float(settings.get("listen.start_timeout_seconds", 5)),
            end_silence_ms=int(settings.get("listen.end_silence_ms", 800)),
            max_seconds=float(settings.get("listen.max_seconds", 15)),
        )
        self.followup_listen = Recorder(
            aggressiveness=int(settings.get("listen.vad_aggressiveness", 3)),
            noise_ratio=float(settings.get("listen.noise_ratio", 2.5)),
            min_level=float(settings.get("listen.min_level", 250)),
            start_timeout=float(settings.get("awake.followup_seconds", 8)),
            end_silence_ms=int(settings.get("listen.end_silence_ms", 800)),
            max_seconds=float(settings.get("listen.max_seconds", 15)),
        )
        self.acks = settings.get("wake.acknowledgements") or ["Yes?"]
        self.sleep_phrases = {_normalize(p) for p in settings.get("awake.sleep_phrases") or []}
        self.brain = brain
        self.state = State.SLEEPING
        # After a conversation ends, plain commands ("open chrome") still work for a while
        # without saying "hey" again.
        self.grace_seconds = float(settings.get("awake.grace_seconds", 60))
        self.join_gap = float(settings.get("listen.end_silence_ms", 1200)) / 1000
        self._last_active = 0.0

    def _load_stt(self) -> None:
        s = self.settings
        log.info("loading speech model")
        try:
            self.stt = Transcriber(
                model=s.get("stt.model", "large-v3-turbo"),
                device=s.get("stt.device", "auto"),
                language=s.get("stt.language"),
                beam_size=int(s.get("stt.beam_size", 1)),
                hotwords=s.get("stt.hotwords"),
            )
            self._stt_ready.set()
        except Exception as e:
            log.exception("speech model failed to load")
            raise RuntimeError("speech model failed to load; voice is off, typing still works") from e

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

    def _in_grace(self) -> bool:
        if self.wake_mode == "always":  # no wake word ever: any command is acted on
            return True
        return time.monotonic() - self._last_active < self.grace_seconds

    def _looks_like_command(self, text: str) -> bool:
        words = [w for w in text.split() if _normalize(w) not in ("okay", "ok", "and", "so", "now", "please", "jarvis")]
        return bool(words) and _verb(words[0]) in self.command_starts

    def _reset_wake(self) -> None:
        if self.wake:
            self.wake.reset()

    def _split_wake(self, text: str) -> tuple[bool, str]:
        """'Hey, open Spotify' -> (True, 'open Spotify'); 'hello there' -> (False, '')."""
        words = text.strip().split()
        if not words:
            return False, ""
        first = _normalize(words[0])
        soft = first in self.soft_wake_words and len(words) > 1 and \
            _verb(words[1]) in self.command_starts
        if first in self.wake_words or soft:
            rest_words = words[1:]
            if rest_words and _normalize(rest_words[0]) == _normalize(self.settings.assistant_name):
                rest_words = rest_words[1:]  # "hey jarvis ..." also works
            rest = " ".join(rest_words).lstrip(",.!? ").strip()
            if soft:  # "he opens spotify" -> "open spotify"
                head, _, tail = rest.partition(" ")
                verb = _verb(head)
                rest = ((verb if verb.startswith(("open", "close", "play", "search", "take", "lock", "start", "launch", "turn", "set", "show", "find", "check")) else head) + (" " + tail if tail else "")).strip()
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
            self._last_active = time.monotonic()
            reply = self.handle(text)
            self._last_active = time.monotonic()
            if reply:
                self.on_event("reply", reply)
                self._say(mic, _brief(reply))
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
            else:  # "phrase" and "always" both listen through speech-to-text
                self._run_phrase(mic)

    def _run_phrase(self, mic: Microphone) -> None:
        """Wake on a spoken phrase ("hey"): every utterance is transcribed locally and
        checked for the wake word at the start. Nothing leaves the PC at this stage."""
        log.info("listening for: %s", ", ".join(sorted(self.wake_words)))
        self._last_active = time.monotonic()  # right after the greeting, commands work without "hey"
        prev_audio: np.ndarray | None = None
        prev_end = 0.0
        while True:
            if self._check_pause():
                mic.read()
                continue
            if not self._stt_ready.is_set():
                mic.read()
                continue
            try:
                audio = self.wake_listen.record(mic, should_stop=lambda: self.paused)
                if audio is None:
                    prev_audio = None
                    continue
                # If you paused mid-sentence, the two halves arrive separately: join them.
                if prev_audio is not None and time.monotonic() - prev_end < self.join_gap + 1.5:
                    audio = np.concatenate([prev_audio, audio])
                text = self.stt.transcribe(audio)  # type: ignore[union-attr]
                prev_audio, prev_end = audio[-16000 * 8:], time.monotonic()  # keep at most 8 s
                woke, rest = self._split_wake(text)
                if not woke and text and self._in_grace() and self._looks_like_command(text):
                    woke, rest = True, text
                    log.info("command heard, no wake word needed")
                if woke:
                    prev_audio = None
                    log.info("wake phrase heard%s", f", with command: {rest}" if rest else "")
                    self._conversation(mic, first_text=rest)
            except Exception:
                # One bad request must never kill the voice loop.
                log.exception("voice request failed; still listening")
                self._set(State.SLEEPING)
                mic.flush()

    def _run_model(self, mic: Microphone) -> None:
        log.info("listening for the wake word model")
        near_miss = 0.0
        while True:
            frame = mic.read()  # keep draining the mic even while paused
            if self._check_pause():
                continue
            if self.wake.detect(frame):  # type: ignore[union-attr]
                near_miss = 0.0
                try:
                    self._conversation(mic)
                except Exception:
                    log.exception("voice request failed; still listening")
                    self._set(State.SLEEPING)
                    mic.flush()
            elif self.wake.last_score > max(0.15, near_miss):  # type: ignore[union-attr]
                near_miss = self.wake.last_score  # type: ignore[union-attr]
                log.info("heard something close to the wake word (score %.2f, needs %.2f)",
                         near_miss, self.wake.threshold)  # type: ignore[union-attr]
            elif self.wake.last_score < 0.05:  # type: ignore[union-attr]
                near_miss = 0.0
