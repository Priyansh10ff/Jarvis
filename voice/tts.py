"""Text to speech on its own thread.

Engines:
    edge  natural Microsoft neural voices (Indian English by default), free, needs internet
    sapi  built-in Windows voices, robotic but fully offline (automatic fallback)

Jarvis plays the audio itself, so speech can be cut off instantly (kill switch)
and the orb pulses with the real voice. Long replies are spoken sentence by
sentence: the next sentence is prepared while the current one plays.

List voices:  python -m voice.tts --list      Test:  python -m voice.tts "Hello Priyansh"
"""
from __future__ import annotations

import asyncio
import logging
import queue
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np

log = logging.getLogger("jarvis.tts")

EDGE_RATE = 24000
EDGE_VOICES = {
    "female": "en-IN-NeerjaNeural",
    "male": "en-IN-PrabhatNeural",
}
HINDI_VOICES = {"female": "hi-IN-SwaraNeural", "male": "hi-IN-MadhurNeural"}
SAPI_PREFERRED = {
    "female": ["heera", "zira", "hazel", "susan"],
    "male": ["ravi", "david", "mark", "george"],
}
DEVANAGARI = re.compile(r"[ऀ-ॿ]")


def _sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?।])\s+", text.strip()) if p.strip()]
    return parts or [text]


class Speaker:
    def __init__(
        self,
        rate: int = 175,
        voice: str | None = "female",
        engine: str = "edge",
        edge_voice: str | None = None,
        on_level: Callable[[float], None] | None = None,
    ) -> None:
        self.rate = rate
        self.gender = (voice or "female").lower() if (voice or "").lower() in ("female", "male") else "female"
        self.voice_pref = voice
        self.engine = engine
        self.edge_voice = edge_voice or EDGE_VOICES[self.gender]
        self.on_level = on_level or (lambda _l: None)
        self._queue: queue.Queue[tuple[str, threading.Event] | None] = queue.Queue()
        self._stop = threading.Event()
        self._sapi = None
        self._synth_pool = ThreadPoolExecutor(max_workers=1)
        self.voice_name = self.edge_voice if engine == "edge" else "windows default"
        self._thread = threading.Thread(target=self._worker, name="tts", daemon=True)
        self._thread.start()
        log.info("voice: %s (%s)", self.voice_name, engine)

    # ── public ───────────────────────────────────────────────────────────────
    def say(self, text: str, wait: bool = True) -> None:
        """Speak text. wait=False returns immediately (used by the typing bar)."""
        if not text or not text.strip():
            return
        done = threading.Event()
        self._queue.put((text, done))
        if wait and not done.wait(timeout=15 + len(text) / 5):
            log.warning("speech took too long; continuing")

    def stop(self) -> None:
        """Cut off current speech and drop anything queued (kill switch)."""
        self._stop.set()
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item:
                item[1].set()
        if self._sapi:
            try:
                self._sapi.stop()
            except Exception:
                pass

    # ── worker ───────────────────────────────────────────────────────────────
    def _worker(self) -> None:
        try:
            import pythoncom

            pythoncom.CoInitialize()  # for the SAPI fallback
        except ImportError:
            pass
        while True:
            item = self._queue.get()
            if item is None:
                return
            text, done = item
            self._stop.clear()
            log.info("say: %s", text)
            try:
                if self.engine == "edge":
                    try:
                        self._speak_edge(text)
                    except Exception as e:
                        log.warning("neural voice failed (%s); using the built-in voice", e)
                        self._speak_sapi(text)
                else:
                    self._speak_sapi(text)
            except Exception:
                log.exception("speech failed")
            finally:
                self.on_level(0.0)
                done.set()

    # edge: synthesize sentence N+1 while sentence N plays
    def _speak_edge(self, text: str) -> None:
        sentences = _sentences(text)
        future = self._synth_pool.submit(self._synth_edge, sentences[0])
        for i in range(len(sentences)):
            pcm = future.result(timeout=20)
            if i + 1 < len(sentences):
                future = self._synth_pool.submit(self._synth_edge, sentences[i + 1])
            if self._stop.is_set():
                return
            self._play(pcm)
            if self._stop.is_set():
                return

    def _synth_edge(self, sentence: str) -> np.ndarray:
        import edge_tts
        import miniaudio

        voice = HINDI_VOICES[self.gender] if DEVANAGARI.search(sentence) else self.edge_voice
        pct = int(round((self.rate - 175) / 175 * 100))  # 175 wpm = normal speed
        rate = f"{pct:+d}%"

        async def fetch() -> bytes:
            data = bytearray()
            async for chunk in edge_tts.Communicate(sentence, voice, rate=rate).stream():
                if chunk["type"] == "audio":
                    data.extend(chunk["data"])
            return bytes(data)

        mp3 = asyncio.run(fetch())
        if not mp3:
            raise RuntimeError("no audio returned")
        decoded = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=EDGE_RATE)
        return np.frombuffer(decoded.samples.tobytes(), dtype=np.int16)

    def _play(self, pcm: np.ndarray) -> None:
        import sounddevice as sd

        block = 1024
        with sd.OutputStream(samplerate=EDGE_RATE, channels=1, dtype="int16", blocksize=block) as out:
            for start in range(0, len(pcm), block):
                if self._stop.is_set():
                    out.abort()
                    return
                chunk = pcm[start:start + block]
                out.write(chunk.reshape(-1, 1))
                rms = float(np.sqrt(np.mean(chunk.astype(np.float32) ** 2))) if len(chunk) else 0.0
                self.on_level(min(1.0, rms / 6000.0))

    # sapi: offline fallback
    def _speak_sapi(self, text: str) -> None:
        if self._sapi is None:
            import pyttsx3

            self._sapi = pyttsx3.init()
            self._sapi.setProperty("rate", self.rate)
            wanted = SAPI_PREFERRED.get((self.voice_pref or "").lower(), [str(self.voice_pref or "").lower()])
            for name in wanted:
                match = next((v for v in self._sapi.getProperty("voices") if name and name in (v.name or "").lower()), None)
                if match:
                    self._sapi.setProperty("voice", match.id)
                    break
        self._sapi.say(text)
        self._sapi.runAndWait()


if __name__ == "__main__":
    import sys

    if "--list" in sys.argv:
        print("Neural voices (voice.edge_voice):")
        for g, v in EDGE_VOICES.items():
            print(f"  {g:<7} {v}")
        print("  more: run  edge-tts --list-voices  (any en-IN / en-US / en-GB voice works)")
        try:
            import pyttsx3

            print("\nOffline Windows voices (voice.engine: sapi):")
            for v in pyttsx3.init().getProperty("voices"):
                print(f"  {v.name}")
        except Exception:
            pass
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        text = " ".join(a for a in sys.argv[1:]) or "Hi Priyansh. This is how I sound now. Pretty natural, right?"
        Speaker().say(text)
