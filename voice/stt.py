"""Speech to text with faster-whisper. GPU when available, CPU fallback."""
from __future__ import annotations

import glob
import logging
import os
import sys
import time

import numpy as np

log = logging.getLogger("jarvis.stt")


def _add_nvidia_dlls() -> None:
    """Let ctranslate2 find cuBLAS/cuDNN installed from pip (Windows)."""
    if sys.platform != "win32":
        return
    for site in sys.path:
        for path in glob.glob(os.path.join(site, "nvidia", "*", "bin")):
            os.add_dll_directory(path)
            os.environ["PATH"] = path + os.pathsep + os.environ.get("PATH", "")


class Transcriber:
    def __init__(
        self,
        model: str = "large-v3-turbo",
        device: str = "auto",
        language: str | None = None,
        beam_size: int = 1,
    ) -> None:
        from faster_whisper import WhisperModel

        _add_nvidia_dlls()
        self.language = language
        self.beam_size = beam_size

        t0 = time.monotonic()
        attempts = [("cuda", "float16"), ("cpu", "int8")] if device == "auto" else [
            (device, "float16" if device == "cuda" else "int8")
        ]
        last_error: Exception | None = None
        for dev, compute in attempts:
            try:
                self._model = WhisperModel(model, device=dev, compute_type=compute)
                self.device = dev
                break
            except Exception as e:  # CUDA missing or out of memory
                log.warning("could not load %s on %s: %s", model, dev, e)
                last_error = e
        else:
            raise RuntimeError(f"Could not load speech model {model}") from last_error
        log.info("speech model %s on %s ready in %.1fs", model, self.device, time.monotonic() - t0)

    def transcribe(self, audio: np.ndarray) -> str:
        t0 = time.monotonic()
        samples = audio.astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(
            samples,
            language=self.language,
            beam_size=self.beam_size,
            condition_on_previous_text=False,
            vad_filter=False,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        log.info(
            "heard (%s, %.0f ms): %s",
            info.language,
            (time.monotonic() - t0) * 1000,
            text or "<nothing>",
        )
        return text


if __name__ == "__main__":
    # Pre-download and test-load the speech model: python -m voice.stt
    import sys as _sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _sys.path.insert(0, ".")
    from core.config import load_settings

    st = load_settings()
    print("Downloading/loading the speech model. First time is ~1.6 GB, progress bars below.")
    Transcriber(model=st.get("stt.model", "large-v3-turbo"), device=st.get("stt.device", "auto"))
    print("Speech model ready.")
