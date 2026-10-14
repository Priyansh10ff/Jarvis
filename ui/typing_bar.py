"""Spotlight-style typing bar: type a command, see the reply."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import QFrame, QLabel, QLineEdit, QVBoxLayout, QWidget

from brain.conversation import Conversation
from core.config import Settings

log = logging.getLogger("jarvis.typing")

STYLE = """
#panel { background: rgba(16, 18, 24, 238); border: 1px solid rgba(120, 200, 255, 60); border-radius: 14px; }
QLineEdit { background: transparent; border: none; color: #f2f4f8; font-size: 18px; padding: 6px 4px; }
#reply { color: #c9d1dc; font-size: 14px; padding: 2px 6px 4px 6px; }
#hint { color: #6b7686; font-size: 11px; padding: 0 6px; }
"""


class TypingBar(QWidget):
    answered = pyqtSignal(str, str)  # (question, reply)

    def __init__(self, settings: Settings, brain: Conversation) -> None:
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.brain = brain
        self.hide_on_blur = bool(settings.get("typing.hide_on_focus_loss", True))
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._busy = False

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet(STYLE)
        self.setFixedWidth(680)

        panel = QFrame(self)
        panel.setObjectName("panel")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(panel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        self.input = QLineEdit()
        self.input.setPlaceholderText(f"Ask {settings.assistant_name}…")
        self.input.setFont(QFont("Segoe UI", 13))
        self.input.returnPressed.connect(self._submit)
        layout.addWidget(self.input)

        self.reply = QLabel()
        self.reply.setObjectName("reply")
        self.reply.setWordWrap(True)
        self.reply.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.reply.hide()
        layout.addWidget(self.reply)

        self.hint = QLabel("Enter to send · Esc to close")
        self.hint.setObjectName("hint")
        layout.addWidget(self.hint)

        self.answered.connect(self._show_reply)

    # ── show / hide ──────────────────────────────────────────────────────────
    def toggle(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.open()

    def open(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.adjustSize()
        self.move(screen.x() + (screen.width() - self.width()) // 2, screen.y() + screen.height() // 4)
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()
        self.input.selectAll()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def changeEvent(self, event) -> None:  # noqa: N802
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow() and self.hide_on_blur:
            self.hide()
        super().changeEvent(event)

    # ── ask the brain off the UI thread ─────────────────────────────────────
    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text or self._busy:
            return
        if text.lower() in ("/quit", "/exit"):
            from PyQt6.QtWidgets import QApplication

            QApplication.quit()
            return
        self._busy = True
        self.input.setReadOnly(True)
        self._set_reply("Thinking…")
        self._pool.submit(self._ask, text)

    def _ask(self, text: str) -> None:
        try:
            answer = self.brain.reply(text)
        except Exception as e:  # never kill the UI
            log.exception("typing bar request failed")
            answer = f"Something went wrong: {e}"
        self.answered.emit(text, answer)

    def _show_reply(self, _question: str, answer: str) -> None:
        self._busy = False
        self.input.setReadOnly(False)
        self.input.clear()
        self._set_reply(answer)

    def _set_reply(self, text: str) -> None:
        self.reply.setText(text)
        self.reply.show()
        self.adjustSize()
