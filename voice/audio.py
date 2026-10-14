"""Microphone input: 16 kHz mono int16 frames."""
from __future__ import annotations

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
FRAME = 1280  # 80 ms, what openWakeWord expects


class Microphone:
    def __init__(self, frame: int = FRAME) -> None:
        self.frame = frame
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=frame
        )

    def __enter__(self) -> "Microphone":
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stream.stop()
        self._stream.close()

    def read(self) -> np.ndarray:
        data, _ = self._stream.read(self.frame)
        return data[:, 0].copy()

    def flush(self) -> None:
        """Drop audio buffered while we were busy (e.g. speaking)."""
        pending = self._stream.read_available
        if pending:
            self._stream.read(pending)
