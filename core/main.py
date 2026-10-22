"""Entry point: python -m core.main

Threads:
    main   Qt event loop (tray, typing bar, hotkeys)
    voice  greeting, wake word, speech in/out
Both share one brain (Conversation), which is thread-safe.
"""
from __future__ import annotations

import logging
import signal
import sys
import threading
import time

from core import single_instance
from core.config import ROOT, Settings, load_settings
from core.greeting import build_greeting
from core.secrets import KNOWN, has_secret

log = logging.getLogger("jarvis")


def setup_logging(level: str, file: str) -> None:
    log_path = ROOT / file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.FileHandler(log_path, encoding="utf-8")]
    if sys.stderr is not None:  # pythonw has no console
        handlers.append(logging.StreamHandler())
    from security.redact import RedactingFilter

    for handler in handlers:
        handler.addFilter(RedactingFilter())  # secrets never reach the log file
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    for noisy in ("comtypes", "httpx", "httpx2", "httpcore", "huggingface_hub", "urllib3", "openai", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def preload(settings: Settings, brain) -> None:
    """Things that are slow the first time: app index, cloud connection."""
    t0 = time.monotonic()
    try:
        from tools.system import installed_apps

        installed_apps()
    except Exception:
        log.exception("app index failed")
    brain.router.warm_up()
    log.info("tools and models ready in %.1fs", time.monotonic() - t0)


def run_voice(settings: Settings, brain, bridge, speaker) -> None:
    """Load everything, greet, then listen. Failures here never take down the typing bar."""
    try:
        t0 = time.monotonic()
        bridge.state_changed.emit("loading")
        warm = threading.Thread(target=preload, args=(settings, brain), name="preload", daemon=True)
        warm.start()

        from core.state import Assistant

        assistant = Assistant(
            settings, speaker, brain, on_state=bridge.state_changed.emit, on_event=bridge.event.emit
        )
        warm.join(timeout=60)
        bridge.assistant = assistant
        log.info("fully loaded in %.1fs", time.monotonic() - t0)

        if settings.get("startup.greet", True):
            speaker.say(build_greeting(settings.user_name, settings.assistant_name))
        assistant.run()
    except Exception:
        log.exception("voice stopped; the typing bar still works")
        bridge.assistant = None
        bridge.state_changed.emit("voice off")


def main(startup: bool = False) -> None:
    settings = load_settings()
    setup_logging(settings.get("logging.level", "INFO"), settings.get("logging.file", "logs/jarvis.log"))

    if not single_instance.acquire():
        log.info("Another instance is already running, exiting.")
        return

    if startup:
        time.sleep(float(settings.get("startup.delay_seconds", 0)))

    from security import audit

    audit.configure(ROOT / settings.get("security.audit_file", "logs/audit.jsonl"))

    for name in KNOWN:
        log.info("key %-10s %s", name, "ok" if has_secret(name) else "missing")

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from brain.conversation import Conversation
    from ui.hotkey import GlobalHotkey
    from ui.overlay import Overlay
    from ui.tray import Tray, VoiceBridge
    from ui.notch import Notch
    from ui.typing_bar import TypingBar

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    brain = Conversation(settings)

    bar = TypingBar(settings, brain)
    bridge = VoiceBridge()
    tray = Tray(settings, brain, bridge, open_bar=bar.open)
    tray.show()
    if settings.get("overlay.enabled", True):
        overlay = Overlay(settings)
        bridge.state_changed.connect(overlay.on_state)
        bridge.event.connect(overlay.on_event)

    if settings.get("typing.notch", True):
        notch = Notch(dwell_ms=int(settings.get("typing.notch_hover_ms", 150)))
        notch.hovered.connect(lambda: (notch.hide(), bar.open_from_notch()))
        bar.closed.connect(notch.show_notch)
        bridge.state_changed.connect(notch.set_state)
        notch.show_notch()

    hotkey = GlobalHotkey(settings.get("typing.hotkey", "ctrl+alt+j"))
    hotkey.pressed.connect(bar.toggle)
    hotkey.start()
    stop_key = GlobalHotkey(settings.get("typing.stop_hotkey", "ctrl+alt+k"))
    stop_key.pressed.connect(tray.kill_switch)
    stop_key.start()
    talk_key = GlobalHotkey(settings.get("listen.push_to_talk_hotkey", "ctrl+alt+space"))
    talk_key.pressed.connect(lambda: bridge.assistant.talk_now() if bridge.assistant else None)
    talk_key.start()

    from voice.tts import Speaker

    speaker = Speaker(
        rate=int(settings.get("voice.tts_rate", 175)),
        voice=settings.get("voice.voice"),
        engine=settings.get("voice.engine", "edge"),
        edge_voice=settings.get("voice.edge_voice"),
        on_level=lambda lvl: bridge.event.emit("speech_level", lvl),  # orb follows the real voice
    )
    if settings.get("typing.speak_replies", True):
        from core.state import _brief

        bar.answered.connect(lambda _q, answer: speaker.say(_brief(answer), wait=False))

    threading.Thread(target=run_voice, args=(settings, brain, bridge, speaker), name="voice", daemon=True).start()

    # Let Ctrl+C in the console stop the Qt loop.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(300)

    log.info("%s online for %s", settings.assistant_name, settings.user_name)
    app.exec()

    hotkey.stop()
    stop_key.stop()
    talk_key.stop()
    tray.hide()
    log.info("stopped")
    logging.shutdown()
    # Model downloads and in-flight requests run in background threads that can keep
    # Python alive for minutes after Quit. Everything is saved, so exit immediately.
    import os

    os._exit(0)


if __name__ == "__main__":
    main()
