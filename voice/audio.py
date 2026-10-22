"""Microphone input: 16 kHz mono int16 frames."""
from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd

log = logging.getLogger("jarvis.audio")

SAMPLE_RATE = 16000
FRAME = 1280  # 80 ms, what openWakeWord expects


def input_devices() -> list[tuple[int, str]]:
    """(index, name) of every device that can record."""
    return [(i, d["name"]) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]


def resolve_device(choice: int | str | None) -> int | None:
    """None = Windows default; int = index; str = part of the device name."""
    if choice is None or choice == "":
        return None
    if isinstance(choice, int) or str(choice).isdigit():
        return int(choice)
    for index, name in input_devices():
        if str(choice).lower() in name.lower():
            return index
    log.warning("no input device matches '%s'; using the default", choice)
    return None


class Microphone:
    def __init__(self, frame: int = FRAME, device: int | str | None = None, gain: float = 1.0) -> None:
        self.frame = frame
        self.gain = gain
        index = resolve_device(device)
        info = sd.query_devices(index, "input")
        self.device_name = info["name"]
        log.info("microphone: %s", self.device_name)
        self._stream = sd.InputStream(
            device=index, samplerate=SAMPLE_RATE, channels=1, dtype="int16", blocksize=frame,
            latency=1.0,  # 1 s buffer: brief pauses in reading (captions, logging) never drop audio
        )

    def __enter__(self) -> "Microphone":
        self._stream.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stream.stop()
        self._stream.close()

    def read(self) -> np.ndarray:
        data, _ = self._stream.read(self.frame)
        frame = data[:, 0].copy()
        if self.gain != 1.0:
            frame = np.clip(frame.astype(np.float32) * self.gain, -32768, 32767).astype(np.int16)
        return frame

    def flush(self) -> None:
        """Drop audio buffered while we were busy (e.g. speaking)."""
        pending = self._stream.read_available
        if pending:
            self._stream.read(pending)
