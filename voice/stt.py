"""Speech to text with faster-whisper. GPU when available, CPU fallback."""
from __future__ import annotations

import glob
import logging
import os
import sys
import time

import numpy as np

# Never let a slow Hugging Face check freeze startup.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "5")
os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")

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
        language: str | None = "en",
        beam_size: int = 1,
        hotwords: str | None = None,
        vocabulary: list[str] | None = None,
    ) -> None:
        from faster_whisper import WhisperModel

        _add_nvidia_dlls()
        self.language = language or None
        self.beam_size = beam_size
        words = [w.strip() for w in (hotwords or "").split(",") if w.strip()] + list(vocabulary or [])
        self.hotwords = ", ".join(dict.fromkeys(words)) or None  # your names/words, spelled right

        t0 = time.monotonic()
        attempts = [("cuda", "float16"), ("cpu", "int8")] if device == "auto" else [
            (device, "float16" if device == "cuda" else "int8")
        ]
        last_error: Exception | None = None
        for dev, compute in attempts:
            try:
                self._model = self._load(WhisperModel, model, dev, compute)
                self.device = dev
                self._test_run()  # CUDA problems often only show up on the first inference
                break
            except Exception as e:  # CUDA/cuDNN missing, out of memory, no model files
                log.warning("speech model on %s failed: %s", dev, e)
                last_error = e
        else:
            raise RuntimeError(f"Could not load speech model {model}") from last_error
        log.info("speech model %s on %s ready in %.1fs", model, self.device, time.monotonic() - t0)

    @staticmethod
    def _load(WhisperModel, model: str, device: str, compute: str):
        """Use the downloaded copy without touching the network; download only if missing."""
        try:
            return WhisperModel(model, device=device, compute_type=compute, local_files_only=True)
        except Exception as e:
            if "local" not in str(e).lower() and "not found" not in str(e).lower() and "snapshot" not in str(e).lower():
                raise
            log.info("speech model not downloaded yet; downloading ~1.6 GB once")
            return WhisperModel(model, device=device, compute_type=compute)

    def _test_run(self) -> None:
        segments, _ = self._model.transcribe(np.zeros(16000, dtype=np.float32), language="en", beam_size=1)
        list(segments)

    def transcribe_partial(self, audio: np.ndarray) -> str:
        """Fast rough pass for live captions while you're still talking (not used for commands)."""
        try:
            segments, _ = self._model.transcribe(
                audio.astype(np.float32) / 32768.0, language=self.language, beam_size=1,
                condition_on_previous_text=False, vad_filter=False, without_timestamps=True,
                hotwords=self.hotwords,
            )
            return " ".join(s.text.strip() for s in segments).strip()
        except Exception:
            return ""

    def warm_up(self) -> None:
        """Kept for callers; the warm-up already happened while loading."""
        return

    def transcribe(self, audio: np.ndarray) -> str:
        t0 = time.monotonic()
        samples = audio.astype(np.float32) / 32768.0
        segments, info = self._model.transcribe(
            samples,
            language=self.language,
            beam_size=self.beam_size,
            condition_on_previous_text=False,
            vad_filter=True,  # Silero VAD trims noise before Whisper sees it
            # threshold 0.35 (default 0.5) keeps quieter speech from a laptop mic
            vad_parameters={"threshold": 0.35, "min_silence_duration_ms": 500, "speech_pad_ms": 300},
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
            hotwords=self.hotwords,
        )
        kept: list[str] = []
        for seg in segments:
            reason = _reject(seg, self.language)
            if reason:
                log.info("ignored segment (%s): %s", reason, seg.text.strip())
                continue
            kept.append(seg.text.strip())
        text = " ".join(kept).strip()
        if _is_noise_text(text):
            if text:
                log.info("ignored (noise): %s", text)
            text = ""
        log.info(
            "heard (%s, %.0f ms): %s",
            info.language,
            (time.monotonic() - t0) * 1000,
            text or "<nothing>",
        )
        return text


# Phrases Whisper is known to invent from silence or noise (from its YouTube training data).
HALLUCINATIONS = {
    "you", "thank you", "thanks for watching", "thank you for watching", "bye", "uh", "um",
    "please subscribe", "subscribe", "so", "okay", "oh", "woo", "ah", "hmm", "e ai", "e aí",
    "ご視聴ありがとうございました", "それでは、ご視聴ありがとうございました",
}


def _reject(seg, language: str | None) -> str | None:
    if seg.no_speech_prob > 0.6 and seg.avg_logprob < -0.7:
        return "probably not speech"
    if seg.avg_logprob < -1.2:
        return "low confidence"
    if seg.compression_ratio > 2.4:
        return "repetitive"
    text = seg.text.strip()
    if language == "en" and text and sum(ord(c) > 127 for c in text) > len(text) / 3:
        return "wrong script"
    return None


def _is_noise_text(text: str) -> bool:
    import re as _re

    cleaned = _re.sub(r"[^\w\s']", "", text.lower(), flags=_re.UNICODE).strip()
    return not cleaned or cleaned in HALLUCINATIONS


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
