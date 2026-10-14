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
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )
    logging.getLogger("comtypes").setLevel(logging.WARNING)  # silence pyttsx3's COM cache noise


def run_voice(settings: Settings, brain, bridge) -> None:
    """Greeting + wake word loop. Failures here never take down the typing bar."""
    try:
        import pythoncom

        pythoncom.CoInitialize()  # speech engine uses COM on this thread
    except ImportError:
        pass

    try:
        from voice.tts import Speaker

        speaker = Speaker(rate=int(settings.get("voice.tts_rate", 175)))
        if settings.get("startup.greet", True):
            speaker.say(build_greeting(settings.user_name, settings.assistant_name))

        from core.state import Assistant

        assistant = Assistant(settings, speaker, brain, on_state=bridge.state_changed.emit)
        bridge.assistant = assistant
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

    for name in KNOWN:
        log.info("key %-10s %s", name, "ok" if has_secret(name) else "missing")

    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from brain.conversation import Conversation
    from ui.hotkey import GlobalHotkey
    from ui.tray import Tray, VoiceBridge
    from ui.typing_bar import TypingBar

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    brain = Conversation(settings)

    bar = TypingBar(settings, brain)
    bridge = VoiceBridge()
    tray = Tray(settings, brain, bridge, open_bar=bar.open)
    tray.show()

    hotkey = GlobalHotkey(settings.get("typing.hotkey", "ctrl+alt+j"))
    hotkey.pressed.connect(bar.toggle)
    hotkey.start()
    stop_key = GlobalHotkey(settings.get("typing.stop_hotkey", "ctrl+alt+k"))
    stop_key.pressed.connect(tray.kill_switch)
    stop_key.start()

    threading.Thread(target=run_voice, args=(settings, brain, bridge), name="voice", daemon=True).start()

    # Let Ctrl+C in the console stop the Qt loop.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.timeout.connect(lambda: None)
    tick.start(300)

    log.info("%s online for %s", settings.assistant_name, settings.user_name)
    app.exec()

    hotkey.stop()
    stop_key.stop()
    tray.hide()
    log.info("stopped")


if __name__ == "__main__":
    main()
