"""Sleep/awake state machine: sleep until the wake word, stay awake until idle."""
from __future__ import annotations

import logging
import random
import time
from enum import Enum

from core.config import Settings
from voice.audio import Microphone
from voice.tts import Speaker
from voice.wakeword import WakeWord

log = logging.getLogger("jarvis.state")


class State(Enum):
    SLEEPING = "sleeping"
    AWAKE = "awake"


class Assistant:
    def __init__(self, settings: Settings, speaker: Speaker) -> None:
        self.settings = settings
        self.speaker = speaker
        self.wake = WakeWord(
            model=settings.get("wake.model", "hey_jarvis"),
            threshold=float(settings.get("wake.threshold", 0.5)),
            cooldown=float(settings.get("wake.cooldown_seconds", 2)),
        )
        self.idle_timeout = float(settings.get("awake.idle_timeout_seconds", 10))
        self.acks = settings.get("wake.acknowledgements") or ["Yes?"]
        self.state = State.SLEEPING
        self._awake_until = 0.0

    def _set(self, state: State) -> None:
        if state != self.state:
            log.info("state: %s -> %s", self.state.value, state.value)
            self.state = state

    def _wake_up(self, mic: Microphone) -> None:
        self._set(State.AWAKE)
        self.speaker.say(random.choice(self.acks))
        mic.flush()          # don't feed our own voice back in
        self.wake.reset()
        self._awake_until = time.monotonic() + self.idle_timeout

    def run(self) -> None:
        log.info("listening for the wake word")
        with Microphone() as mic:
            while True:
                frame = mic.read()
                if self.state is State.SLEEPING:
                    if self.wake.detect(frame):
                        self._wake_up(mic)
                else:
                    # Speech-to-text plugs in here in the next feature.
                    if self.wake.detect(frame):
                        self._wake_up(mic)
                    elif time.monotonic() >= self._awake_until:
                        self._set(State.SLEEPING)
