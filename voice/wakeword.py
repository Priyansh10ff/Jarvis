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
    """Live check: python -m voice.wakeword   (add --list to see microphones)"""
    import sys

    from core.config import load_settings
    from voice.audio import Microphone, input_devices

    if "--list" in sys.argv:
        for index, name in input_devices():
            print(f"{index:>3}  {name}")
        print("\nSet one in config/settings.yaml:  audio.input_device: <number or part of the name>")
        return

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    st = load_settings()
    threshold = float(st.get("wake.threshold", 0.5))
    wake = WakeWord(model=st.get("wake.model", "hey_jarvis"), threshold=threshold)
    mic = Microphone(device=st.get("audio.input_device"), gain=float(st.get("audio.gain", 1.0)))
    print(f"\nMic: {mic.device_name}   threshold: {threshold}")
    print("Say 'Hey Jarvis' a few times. The bar is your mic volume. Ctrl+C to stop.\n")

    peak_level = peak_score = 0.0
    frames = 0
    with mic:
        while True:
            frame = mic.read()
            hit = wake.detect(frame)
            level = float(np.sqrt(np.mean(frame.astype(np.float32) ** 2)))
            peak_level = max(peak_level, level)
            peak_score = max(peak_score, wake.last_score)
            frames += 1
            if hit:
                print(f"  >>> WAKE  (score {wake.last_score:.2f})")
            if frames % 6 == 0:  # about twice a second
                bar = "#" * min(40, int(peak_level / 150))
                hint = "  (too quiet?)" if peak_level < 300 else ""
                print(f"mic {int(peak_level):>5} |{bar:<40}| score {peak_score:.2f}{hint}")
                peak_level = peak_score = 0.0


if __name__ == "__main__":
    try:
        _demo()
    except KeyboardInterrupt:
        pass
