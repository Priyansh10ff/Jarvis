"""Tray icon: shows state, pause/resume listening, kill switch, model choice, quit."""
from __future__ import annotations

import logging
import os

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from brain.conversation import Conversation
from core.config import ROOT, Settings

log = logging.getLogger("jarvis.tray")

COLORS = {
    "starting": "#5a6472",
    "sleeping": "#2f8fb8",
    "awake": "#38d6ff",
    "paused": "#7a7f88",
    "voice off": "#b85a2f",
}


def _icon(color: str) -> QIcon:
    """A small glowing orb, drawn in code so there is no image file to ship."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    glow = QRadialGradient(32, 32, 30)
    c = QColor(color)
    glow.setColorAt(0.0, QColor(255, 255, 255))
    glow.setColorAt(0.35, c)
    c.setAlpha(0)
    glow.setColorAt(1.0, c)
    p.setBrush(glow)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 60, 60)
    p.end()
    return QIcon(pix)


class VoiceBridge(QObject):
    """Carries voice-thread state to the UI thread."""

    state_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self.assistant = None  # set by the voice thread once it is running


class Tray(QSystemTrayIcon):
    def __init__(self, settings: Settings, brain: Conversation, bridge: VoiceBridge, open_bar) -> None:
        super().__init__()
        self.settings = settings
        self.brain = brain
        self.bridge = bridge
        self.state = "starting"

        menu = QMenu()
        menu.addAction("Open typing bar", open_bar)

        self.pause_action = QAction("Pause listening", menu)
        self.pause_action.triggered.connect(self.toggle_pause)
        self.pause_action.setEnabled(False)
        menu.addAction(self.pause_action)

        menu.addAction("Stop now", self.kill_switch)
        menu.addSeparator()

        model_menu = menu.addMenu("Model")
        group = QActionGroup(model_menu)
        available = set(brain.router.available())
        for label, name in [("Auto", None), ("Groq", "groq"), ("Claude", "claude"), ("Local", "local")]:
            act = QAction(label, model_menu, checkable=True)
            act.setChecked(name is None)
            act.setEnabled(name is None or name in available)
            act.triggered.connect(lambda _=False, n=name: self._prefer(n))
            group.addAction(act)
            model_menu.addAction(act)

        menu.addAction("Open log", self._open_log)
        menu.addSeparator()
        menu.addAction("Quit", QApplication.quit)

        self._menu = menu  # keep a reference
        self.setContextMenu(menu)
        self.activated.connect(self._on_click)
        bridge.state_changed.connect(self.set_state)
        self.set_state("starting")

    def set_state(self, state: str) -> None:
        self.state = state
        self.setIcon(_icon(COLORS.get(state, COLORS["sleeping"])))
        self.setToolTip(f"{self.settings.assistant_name}: {state}")
        if state != "starting":
            self.pause_action.setEnabled(self.bridge.assistant is not None)
        self.pause_action.setText("Resume listening" if state == "paused" else "Pause listening")

    def toggle_pause(self) -> None:
        assistant = self.bridge.assistant
        if not assistant:
            return
        if assistant.paused:
            assistant.resume()
            log.info("listening resumed")
        else:
            assistant.pause()
            log.info("listening paused")

    def kill_switch(self) -> None:
        log.info("kill switch")
        if self.bridge.assistant:
            self.bridge.assistant.interrupt()
        else:
            self.brain.cancel_pending()

    def _prefer(self, name: str | None) -> None:
        self.brain.router.prefer(name)
        log.info("model preference: %s", name or "auto")

    def _open_log(self) -> None:
        path = ROOT / self.settings.get("logging.file", "logs/jarvis.log")
        if path.exists() and hasattr(os, "startfile"):
            os.startfile(path)

    def _on_click(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.contextMenu().actions()[0].trigger()
