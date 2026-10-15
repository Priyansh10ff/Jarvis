"""Record one utterance: wait for speech, stop after a pause (WebRTC VAD)."""
from __future__ import annotations

import logging
import time
from collections import deque
from typing import Callable

import numpy as np
import webrtcvad

from voice.audio import SAMPLE_RATE, Microphone

log = logging.getLogger("jarvis.listen")

SUB = 320  # 20 ms at 16 kHz, a frame size WebRTC VAD accepts


class NoiseFloor:
    """Tracks background loudness (fans, traffic, chatter far away). Shared across recorders."""

    def __init__(self) -> None:
        self.level = 0.0

    def update(self, rms: float, voiced: bool) -> None:
        if self.level == 0.0:
            self.level = rms
        elif not voiced:
            self.level = 0.95 * self.level + 0.05 * rms   # adapt to steady background
        else:
            self.level = 0.999 * self.level + 0.001 * rms  # barely move while you talk


NOISE = NoiseFloor()


class Recorder:
    def __init__(
        self,
        aggressiveness: int = 3,
        start_timeout: float = 5.0,
        end_silence_ms: int = 800,
        max_seconds: float = 15.0,
        noise_ratio: float = 2.5,
        min_level: float = 250.0,
    ) -> None:
        self.vad = webrtcvad.Vad(aggressiveness)
        self.start_timeout = start_timeout
        self.end_silence_ms = end_silence_ms
        self.max_seconds = max_seconds
        self.noise_ratio = noise_ratio  # speech must be this many times louder than the background
        self.min_level = min_level      # and at least this loud (int16 RMS)

    def _voiced(self, frame: np.ndarray, started: bool = False) -> bool:
        subs = [frame[i : i + SUB] for i in range(0, len(frame) - SUB + 1, SUB)]
        hits = sum(self.vad.is_speech(s.tobytes(), SAMPLE_RATE) for s in subs)
        speechy = hits * 2 >= len(subs)
        rms = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
        if not started:
            # Starting a sentence: must be clearly louder than the room.
            voiced = speechy and rms >= max(self.min_level, NOISE.level * self.noise_ratio)
        else:
            # Mid-sentence: quieter syllables still count, so you aren't cut off.
            voiced = (speechy and rms >= NOISE.level * 1.2) or rms >= max(self.min_level, NOISE.level * 1.8)
        NOISE.update(rms, voiced)
        return voiced

    def record(
        self,
        mic: Microphone,
        should_stop: Callable[[], bool] = lambda: False,
        on_frame: Callable[[np.ndarray], None] | None = None,
    ) -> np.ndarray | None:
        """Return int16 audio of one utterance, or None if nobody spoke."""
        frame_ms = mic.frame * 1000 // SAMPLE_RATE
        # Keep ~0.65 s from before speech was detected, so a short first word ("hey") isn't cut off.
        preroll: deque[np.ndarray] = deque(maxlen=max(1, 650 // frame_ms))
        frames: list[np.ndarray] = []
        started = False
        speech_ms = silence_ms = 0
        deadline = time.monotonic() + self.start_timeout

        while True:
            if should_stop():
                return None
            frame = mic.read()
            if on_frame:
                on_frame(frame)
            voiced = self._voiced(frame, started)

            if not started:
                preroll.append(frame)
                speech_ms = speech_ms + frame_ms if voiced else 0
                if speech_ms >= 160:
                    started = True
                    frames = list(preroll)
                elif time.monotonic() > deadline:
                    return None
                continue

            frames.append(frame)
            silence_ms = 0 if voiced else silence_ms + frame_ms
            if silence_ms >= self.end_silence_ms:
                break
            if len(frames) * frame_ms >= self.max_seconds * 1000:
                log.info("hit max utterance length")
                break

        return np.concatenate(frames)
