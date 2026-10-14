"""Wake word detection with openWakeWord (runs on CPU, ~1-2% load).

Test and tune the threshold:
    python -m voice.wakeword
"""
from __future__ import annotations

import logging
import time

import numpy as np

log = logging.getLogger("jarvis.wake")


class WakeWord:
    def __init__(self, model: str = "hey_jarvis", threshold: float = 0.5, cooldown: float = 2.0) -> None:
        from openwakeword.model import Model
        from openwakeword.utils import download_models

        try:
            download_models(model_names=[model])
        except Exception:
            log.warning("Could not download wake word models; using any cached copy")

        self._model = Model(wakeword_models=[model], inference_framework="onnx")
        self.threshold = threshold
        self.cooldown = cooldown
        self._last_hit = 0.0
        self.last_score = 0.0

    def detect(self, frame: np.ndarray) -> bool:
        scores = self._model.predict(frame)
        self.last_score = max(scores.values()) if scores else 0.0
        now = time.monotonic()
        if self.last_score >= self.threshold and now - self._last_hit >= self.cooldown:
            self._last_hit = now
            log.info("wake word (score %.2f)", self.last_score)
            self.reset()
            return True
        return False

    def reset(self) -> None:
        self._model.reset()


def _demo() -> None:
    from voice.audio import Microphone

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    wake = WakeWord()
    print("Say 'Hey Jarvis'. Scores above 0.10 are shown. Ctrl+C to stop.")
    with Microphone() as mic:
        while True:
            hit = wake.detect(mic.read())
            if wake.last_score > 0.1 or hit:
                print(f"score {wake.last_score:.2f}{'  <- WAKE' if hit else ''}")


if __name__ == "__main__":
    try:
        _demo()
    except KeyboardInterrupt:
        pass
