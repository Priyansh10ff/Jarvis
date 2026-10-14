"""Record one utterance: wait for speech, stop after a pause (WebRTC VAD)."""
from __future__ import annotations

import logging
import time
from collections import deque

import numpy as np
import webrtcvad

from voice.audio import SAMPLE_RATE, Microphone

log = logging.getLogger("jarvis.listen")

SUB = 320  # 20 ms at 16 kHz, a frame size WebRTC VAD accepts


class Recorder:
    def __init__(
        self,
        aggressiveness: int = 2,
        start_timeout: float = 5.0,
        end_silence_ms: int = 800,
        max_seconds: float = 15.0,
    ) -> None:
        self.vad = webrtcvad.Vad(aggressiveness)
        self.start_timeout = start_timeout
        self.end_silence_ms = end_silence_ms
        self.max_seconds = max_seconds

    def _voiced(self, frame: np.ndarray) -> bool:
        subs = [frame[i : i + SUB] for i in range(0, len(frame) - SUB + 1, SUB)]
        hits = sum(self.vad.is_speech(s.tobytes(), SAMPLE_RATE) for s in subs)
        return hits * 2 >= len(subs)

    def record(self, mic: Microphone) -> np.ndarray | None:
        """Return int16 audio of one utterance, or None if nobody spoke."""
        frame_ms = mic.frame * 1000 // SAMPLE_RATE
        preroll: deque[np.ndarray] = deque(maxlen=max(1, 300 // frame_ms))
        frames: list[np.ndarray] = []
        started = False
        speech_ms = silence_ms = 0
        deadline = time.monotonic() + self.start_timeout

        while True:
            frame = mic.read()
            voiced = self._voiced(frame)

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
