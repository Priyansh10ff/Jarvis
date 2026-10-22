"""Holographic orb overlay: appears on wake, reacts to your voice, pulses while talking.

Transparent, always on top, never takes focus and ignores mouse clicks.
An original design (rings + glowing core), drawn in code at ~60 fps.
"""
from __future__ import annotations

import math
import random
import time

from PyQt6.QtCore import QPropertyAnimation, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QWidget

from core.config import Settings

CYAN = QColor(56, 214, 255)
VIOLET = QColor(150, 120, 255)
CAPTION_H = 76


class Overlay(QWidget):
    def __init__(self, settings: Settings) -> None:
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.orb = int(settings.get("overlay.size", 220))
        self.position = settings.get("overlay.position", "bottom-right")
        self.captions = bool(settings.get("overlay.show_captions", True))
        self.setFixedSize(max(self.orb, 360), self.orb + (CAPTION_H if self.captions else 0))

        self.activity = "listening"  # listening | thinking | speaking
        self.level = 0.0             # smoothed 0..1
        self._target = 0.0
        self.caption = ""
        self._t0 = time.monotonic()
        self._speech_level = 0.0
        self._speech_at = 0.0

        self._fade = QPropertyAnimation(self, b"windowOpacity")
        self._fade.setDuration(220)
        self._fade.finished.connect(self._after_fade)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ── signals from the voice thread ───────────────────────────────────────
    def on_state(self, state: str) -> None:
        if state == "awake":
            self.caption = ""
            self.activity = "listening"
            self._appear()
        elif state in ("sleeping", "paused", "voice off"):
            self._disappear()

    def on_event(self, kind: str, value: object) -> None:
        if kind == "activity":
            self.activity = str(value)
        elif kind == "level":
            self._target = float(value)
        elif kind == "speech_level":
            self._speech_level = float(value)
            self._speech_at = time.monotonic()
        elif kind == "partial":
            self.caption = f"{value}…"
        elif kind == "heard":
            self.caption = f"“{value}”"
        elif kind == "reply":
            self.caption = str(value)

    # ── show / hide ─────────────────────────────────────────────────────────
    def _place(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        margin = 24
        if self.position == "center":
            x = screen.x() + (screen.width() - self.width()) // 2
            y = screen.y() + (screen.height() - self.height()) // 2
        elif self.position == "bottom-center":
            x = screen.x() + (screen.width() - self.width()) // 2
            y = screen.y() + screen.height() - self.height() - margin
        else:
            x = screen.x() + screen.width() - self.width() - margin
            y = screen.y() + screen.height() - self.height() - margin
        self.move(x, y)

    def _appear(self) -> None:
        self._place()
        if not self.isVisible():
            self.setWindowOpacity(0.0)
            self.show()
        self._timer.start(16)
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(1.0)
        self._fade.start()

    def _disappear(self) -> None:
        if not self.isVisible():
            return
        self._fade.stop()
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _after_fade(self) -> None:
        if self.windowOpacity() <= 0.01:
            self.hide()
            self._timer.stop()

    # ── animation ───────────────────────────────────────────────────────────
    def _tick(self) -> None:
        t = time.monotonic() - self._t0
        if self.activity == "speaking":
            if time.monotonic() - self._speech_at < 0.25:
                self._target = 0.2 + 0.8 * self._speech_level  # real voice level
            else:  # offline voice gives no levels: animate procedurally
                self._target = 0.35 + 0.45 * abs(math.sin(t * 9.0) * math.sin(t * 3.3)) + random.uniform(0, 0.1)
        elif self.activity == "thinking":
            self._target = 0.25 + 0.1 * math.sin(t * 4)
        self.level += (self._target - self.level) * 0.25
        if self.activity == "listening":
            self._target *= 0.9  # decay between mic frames
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = time.monotonic() - self._t0
        cx, cy = self.width() / 2, self.orb / 2
        r = self.orb * 0.30
        color = VIOLET if self.activity == "thinking" else CYAN
        lvl = self.level

        # outer glow
        glow = QRadialGradient(cx, cy, r * 1.7)
        g = QColor(color)
        g.setAlpha(int(70 + 110 * lvl))
        glow.setColorAt(0.0, g)
        g.setAlpha(0)
        glow.setColorAt(1.0, g)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(QRectF(cx - r * 1.7, cy - r * 1.7, r * 3.4, r * 3.4))

        # rotating rings
        speed = 2.6 if self.activity == "thinking" else 1.0
        for i, (scale, span, width, rate) in enumerate(
            [(1.05, 250, 2.0, 40), (1.22, 110, 1.4, -65), (1.38, 70, 1.0, 95)]
        ):
            rr = r * (scale + 0.06 * lvl)
            c = QColor(color)
            c.setAlpha(200 - i * 45)
            p.setPen(QPen(c, width, cap=Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            start = int((t * rate * speed) % 360 * 16)
            p.drawArc(QRectF(cx - rr, cy - rr, rr * 2, rr * 2), start, span * 16)
            p.drawArc(QRectF(cx - rr, cy - rr, rr * 2, rr * 2), start + 180 * 16, int(span * 0.4) * 16)

        # core
        core_r = r * (0.55 + 0.30 * lvl)
        core = QRadialGradient(cx, cy, core_r)
        core.setColorAt(0.0, QColor(255, 255, 255, 240))
        mid = QColor(color)
        mid.setAlpha(220)
        core.setColorAt(0.45, mid)
        mid.setAlpha(0)
        core.setColorAt(1.0, mid)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(core)
        p.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2, core_r * 2))

        # caption
        if self.captions and self.caption:
            p.setFont(QFont("Segoe UI", 10))
            box = QRectF(8, self.orb + 4, self.width() - 16, CAPTION_H - 8)
            p.setPen(QColor(0, 0, 0, 170))
            p.drawText(box.translated(1, 1), Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, self.caption)
            p.setPen(QColor(235, 245, 255))
            p.drawText(box, Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap, self.caption)
        p.end()
