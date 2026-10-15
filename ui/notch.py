"""Notch: a thin glowing pill at the top-center of the screen.

Always there, never takes focus. Rest the mouse on it and the typing bar drops
down; move away and the bar folds back into the notch. Its glow shows Jarvis's
state (blue sleeping, cyan awake, grey paused).
"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QWidget

COLORS = {
    "starting": QColor(90, 100, 114),
    "loading": QColor(90, 100, 114),
    "sleeping": QColor(47, 143, 184),
    "awake": QColor(56, 214, 255),
    "paused": QColor(122, 127, 136),
    "voice off": QColor(184, 90, 47),
}

PILL_W, PILL_H = 140, 6
HOVER_W, HOVER_H = 190, 10
WIN_W, WIN_H = 260, 22  # a little larger than the pill so it's easy to hit


class Notch(QWidget):
    hovered = pyqtSignal()

    def __init__(self, dwell_ms: int = 150) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(WIN_W, WIN_H)
        self.setMouseTracking(True)
        self.color = COLORS["starting"]
        self._hover = False

        # Require the mouse to rest briefly, so flicking past the top edge doesn't open it.
        self._dwell = QTimer(self, singleShot=True, interval=dwell_ms)
        self._dwell.timeout.connect(self._fire)

    def place(self) -> None:
        screen = QGuiApplication.primaryScreen().geometry()  # full screen: sit on the very top edge
        self.move(screen.x() + (screen.width() - WIN_W) // 2, screen.y())

    def show_notch(self) -> None:
        self.place()
        self.show()
        self.raise_()

    def set_state(self, state: str) -> None:
        self.color = COLORS.get(state, COLORS["sleeping"])
        self.update()

    def enterEvent(self, _event) -> None:  # noqa: N802
        self._hover = True
        self.update()
        self._dwell.start()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self._hover = False
        self._dwell.stop()
        self.update()

    def mousePressEvent(self, _event) -> None:  # noqa: N802
        self._fire()

    def _fire(self) -> None:
        self._hover = False
        self.hovered.emit()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = (HOVER_W, HOVER_H) if self._hover else (PILL_W, PILL_H)
        rect = QRectF((WIN_W - w) / 2, 2, w, h)

        glow = QColor(self.color)
        glow.setAlpha(70)
        p.setPen(QPen(glow, 4))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, h / 2, h / 2)

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(16, 18, 24, 235))
        p.drawRoundedRect(rect, h / 2, h / 2)

        line = QColor(self.color)
        line.setAlpha(230)
        p.setPen(QPen(line, 1.5))
        inner = rect.adjusted(w * 0.3, h / 2 - 0.5, -w * 0.3, -(h / 2 - 0.5))
        p.drawLine(inner.topLeft(), inner.topRight())
        p.end()
