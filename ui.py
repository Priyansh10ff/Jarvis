import sys
import os
import threading
import math
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QScrollArea, QFrame, QDialog,
    QListWidget, QListWidgetItem, QMessageBox, QSlider, QComboBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPointF
from PyQt6.QtGui import (
    QFont, QPainter, QPen, QBrush, QColor,
    QRadialGradient, QPolygonF, QPainterPath
)

# ── Jarvis Color Palette ─────────────────────────────────────────────────────
J_BLACK   = "#000408"
J_NAVY    = "#010d1a"
J_BLUE    = "#0a4d8c"
J_CYAN    = "#00d4ff"
J_GLOW    = "#00f0ff"
J_DIM     = "#003d5c"
J_GOLD    = "#ffa500"
J_RED     = "#ff2244"
J_TEXT    = "#c8f0ff"
J_MUTED   = "#3a7a99"
J_BORDER  = "#0d3a52"
J_SUCCESS = "#00ff88"

STYLE = f"""
QMainWindow, QWidget {{
    background-color: {J_BLACK};
    color: {J_TEXT};
    font-family: 'Courier New', monospace;
}}
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: {J_NAVY};
    width: 4px;
    border-radius: 2px;
}}
QScrollBar::handle:vertical {{
    background: {J_CYAN};
    border-radius: 2px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
QTextEdit {{
    background: {J_NAVY};
    color: {J_CYAN};
    border: 1px solid {J_BLUE};
    border-radius: 4px;
    padding: 10px;
    font-size: 13px;
    font-family: 'Courier New', monospace;
    selection-background-color: {J_BLUE};
}}
QTextEdit:focus {{ border: 1px solid {J_CYAN}; }}
QPushButton {{
    border-radius: 2px;
    font-size: 11px;
    font-weight: bold;
    font-family: 'Courier New', monospace;
    padding: 8px 16px;
    border: 1px solid {J_CYAN};
    color: {J_CYAN};
    background: transparent;
    letter-spacing: 2px;
}}
QPushButton:hover {{
    background: rgba(0, 212, 255, 0.1);
    border-color: {J_GLOW};
    color: {J_GLOW};
}}
QPushButton:pressed {{ background: rgba(0, 212, 255, 0.2); }}
QPushButton:disabled {{ border-color: {J_BORDER}; color: {J_MUTED}; }}
QLabel {{ color: {J_TEXT}; font-family: 'Courier New', monospace; }}
QListWidget {{
    background: {J_NAVY};
    border: 1px solid {J_BORDER};
    border-radius: 2px;
    color: {J_TEXT};
    font-size: 12px;
    font-family: 'Courier New', monospace;
    padding: 4px;
}}
QListWidget::item {{
    padding: 8px;
    border-bottom: 1px solid {J_BORDER};
}}
QListWidget::item:selected {{
    background: rgba(0, 212, 255, 0.15);
    color: {J_CYAN};
    border-left: 2px solid {J_CYAN};
}}
QListWidget::item:hover {{ background: rgba(0, 212, 255, 0.07); }}
QComboBox {{
    background: {J_NAVY};
    border: 1px solid {J_BLUE};
    border-radius: 2px;
    color: {J_CYAN};
    padding: 6px 10px;
    font-size: 12px;
    font-family: 'Courier New', monospace;
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {J_NAVY};
    color: {J_CYAN};
    border: 1px solid {J_BLUE};
    selection-background-color: rgba(0,212,255,0.15);
}}
QSlider::groove:horizontal {{
    background: {J_BORDER};
    height: 2px;
    border-radius: 1px;
}}
QSlider::handle:horizontal {{
    background: {J_CYAN};
    width: 12px;
    height: 12px;
    margin: -5px 0;
    border-radius: 6px;
    border: 1px solid {J_GLOW};
}}
QSlider::sub-page:horizontal {{
    background: {J_CYAN};
    border-radius: 1px;
}}
QDialog {{ background: {J_BLACK}; border: 1px solid {J_BLUE}; }}
"""


# ── Arc Reactor Widget ───────────────────────────────────────────────────────
class ArcReactor(QWidget):
    def __init__(self, size=80, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._pulse = 0.0
        self._pulse_dir = 1
        self._active = False
        self._listening = False
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(16)

    def set_active(self, v):    self._active = v
    def set_listening(self, v): self._listening = v

    def _tick(self):
        self._angle = (self._angle + 2) % 360
        self._pulse += 0.04 * self._pulse_dir
        if self._pulse >= 1.0:  self._pulse_dir = -1
        if self._pulse <= 0.0:  self._pulse_dir = 1
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = min(cx, cy) - 4

        color = J_GLOW if self._listening else (J_CYAN if self._active else J_DIM)

        # outer ring
        pen = QPen(QColor(color)); pen.setWidth(2)
        p.setPen(pen); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # spinning dashes
        for i in range(8):
            ang = math.radians(self._angle + i * 45)
            x1 = cx + (r - 6) * math.cos(ang); y1 = cy + (r - 6) * math.sin(ang)
            x2 = cx + r * math.cos(ang);        y2 = cy + r * math.sin(ang)
            c = QColor(color); c.setAlpha(max(30, 255 - i * 28))
            pp = QPen(c); pp.setWidth(2); p.setPen(pp)
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # inner hexagon
        hr = r * 0.55
        hex_pts = QPolygonF([QPointF(cx + hr * math.cos(math.radians(60*i+30)),
                                     cy + hr * math.sin(math.radians(60*i+30))) for i in range(6)])
        pen2 = QPen(QColor(color)); pen2.setWidth(1)
        p.setPen(pen2); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPolygon(hex_pts)

        # core glow
        cr = r * 0.28
        g = QRadialGradient(cx, cy, cr)
        g.setColorAt(0, QColor(color))
        g.setColorAt(0.5, QColor(J_CYAN).darker(180))
        g.setColorAt(1, QColor(J_NAVY))
        p.setBrush(QBrush(g)); p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), cr, cr)

        # pulse ring
        pr = r * (0.65 + 0.1 * self._pulse)
        c2 = QColor(color); c2.setAlpha(int(40 * self._pulse))
        pp2 = QPen(c2); pp2.setWidth(1); p.setPen(pp2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), pr, pr)
        p.end()


# ── Waveform Widget ──────────────────────────────────────────────────────────
class WaveformWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self._bars = [0.0] * 32
        self._active = False
        t = QTimer(self); t.timeout.connect(self._tick); t.start(50)

    def set_active(self, v): self._active = v

    def _tick(self):
        import random
        if self._active:
            self._bars = [random.uniform(0.1, 1.0) for _ in self._bars]
        else:
            self._bars = [max(0.0, b - 0.15) for b in self._bars]
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        bw = w / len(self._bars)
        for i, bar in enumerate(self._bars):
            bh = bar * (h - 4)
            x = i * bw + 1; y = (h - bh) / 2
            c = QColor(J_CYAN); c.setAlpha(int(80 + 175 * bar))
            p.setBrush(QBrush(c)); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(int(x), int(y), max(2, int(bw - 2)), max(1, int(bh)), 1, 1)
        p.end()


# ── Chat Message ─────────────────────────────────────────────────────────────
class JarvisMessage(QWidget):
    def __init__(self, text, sender="ai", timestamp="", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)
        is_user = sender == "user"
        if is_user: layout.addStretch()

        bubble = QFrame()
        bubble.setMaximumWidth(580)
        bl = QVBoxLayout(bubble)
        bl.setContentsMargins(14, 10, 14, 10)
        bl.setSpacing(4)

        hdr = QHBoxLayout()
        tag = QLabel("[ PRIYANSH ]" if is_user else "[ J.A.R.V.I.S ]")
        tag.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        tag.setStyleSheet(f"color: {J_GOLD if is_user else J_CYAN}; background: transparent;")
        hdr.addWidget(tag); hdr.addStretch()
        ts = QLabel(timestamp)
        ts.setFont(QFont("Courier New", 8))
        ts.setStyleSheet(f"color: {J_MUTED}; background: transparent;")
        hdr.addWidget(ts)
        bl.addLayout(hdr)

        msg = QLabel(text)
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg.setFont(QFont("Courier New", 12))
        msg.setStyleSheet(f"color: {J_TEXT}; background: transparent;")
        bl.addWidget(msg)

        bubble.setStyleSheet(f"""
            QFrame {{
                background: rgba({'255,165,0' if is_user else '0,212,255'}, 0.04);
                border: 1px solid rgba({'255,165,0' if is_user else '0,212,255'}, 0.2);
                border-left: 2px solid {J_GOLD if is_user else J_CYAN};
                border-radius: 2px;
            }}
        """)
        layout.addWidget(bubble)
        if not is_user: layout.addStretch()


# ── Memory Dialog ─────────────────────────────────────────────────────────────
class MemoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("J.A.R.V.I.S — Memory Core")
        self.setMinimumSize(680, 540)
        self.setStyleSheet(STYLE)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        hdr = QLabel("◈ MEMORY CORE ACCESS")
        hdr.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {J_CYAN}; letter-spacing: 4px;")
        layout.addWidget(hdr)

        line = QFrame(); line.setFixedHeight(1)
        line.setStyleSheet(f"background: {J_BLUE};")
        layout.addWidget(line)

        sub = QLabel("// Stored interaction logs and learned preferences")
        sub.setStyleSheet(f"color: {J_MUTED}; font-size: 11px;")
        layout.addWidget(sub)

        self.memory_list = QListWidget()
        layout.addWidget(self.memory_list)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("REFRESH")
        self.delete_btn  = QPushButton("DELETE SELECTED")
        self.clear_btn   = QPushButton("PURGE ALL")
        self.delete_btn.setStyleSheet(f"border-color: {J_RED}; color: {J_RED};")
        self.clear_btn.setStyleSheet(f"border-color: {J_RED}; color: {J_RED};")
        self.refresh_btn.clicked.connect(self.load_memories)
        self.delete_btn.clicked.connect(self.delete_selected)
        self.clear_btn.clicked.connect(self.clear_all)
        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.delete_btn)
        btn_row.addWidget(self.clear_btn)
        layout.addLayout(btn_row)

        self.count_lbl = QLabel("")
        self.count_lbl.setStyleSheet(f"color: {J_MUTED}; font-size: 11px;")
        layout.addWidget(self.count_lbl)
        self.load_memories()

    def load_memories(self):
        self.memory_list.clear()
        try:
            import chromadb
            client = chromadb.PersistentClient(path="memory")
            col = client.get_or_create_collection("agent_memory")
            res = col.get()
            docs, ids = res.get('documents', []), res.get('ids', [])
            for i, (doc, mid) in enumerate(zip(docs, ids)):
                item = QListWidgetItem(f"[{i+1:03d}] {doc[:110]}{'...' if len(doc)>110 else ''}")
                item.setData(Qt.ItemDataRole.UserRole, mid)
                self.memory_list.addItem(item)
            self.count_lbl.setText(f"// {len(docs)} memory entries loaded")
        except Exception as ex:
            self.count_lbl.setText(f"// Error: {ex}")

    def delete_selected(self):
        selected = self.memory_list.selectedItems()
        if not selected: return
        try:
            import chromadb
            client = chromadb.PersistentClient(path="memory")
            col = client.get_or_create_collection("agent_memory")
            for item in selected:
                col.delete(ids=[item.data(Qt.ItemDataRole.UserRole)])
            self.load_memories()
        except Exception as ex:
            QMessageBox.critical(self, "Error", str(ex))

    def clear_all(self):
        if QMessageBox.question(self, "Purge All", "Purge ALL memory? Cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                import chromadb
                client = chromadb.PersistentClient(path="memory")
                client.delete_collection("agent_memory")
                client.get_or_create_collection("agent_memory")
                self.load_memories()
            except Exception as ex:
                QMessageBox.critical(self, "Error", str(ex))


# ── Main Window ───────────────────────────────────────────────────────────────
class JarvisWindow(QMainWindow):
    add_msg_signal   = pyqtSignal(str, str)
    status_signal    = pyqtSignal(str, str)
    mem_count_signal = pyqtSignal(int)
    reactor_signal   = pyqtSignal(bool, bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("J.A.R.V.I.S — Personal AI")
        self.setMinimumSize(1000, 720)
        self.resize(1200, 820)
        self.setStyleSheet(STYLE)
        self.agent_running = False
        self._build_ui()
        self._connect_signals()
        self._update_memory_count()
        QTimer(self, timeout=lambda: self.clock_lbl.setText(datetime.now().strftime("%H:%M:%S")),
               interval=1000).start()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top bar ──
        topbar = QFrame()
        topbar.setFixedHeight(72)
        topbar.setStyleSheet(f"background: {J_NAVY}; border-bottom: 1px solid {J_BLUE};")
        tb = QHBoxLayout(topbar)
        tb.setContentsMargins(20, 0, 20, 0)

        left = QHBoxLayout(); left.setSpacing(14)
        self.reactor = ArcReactor(56)
        left.addWidget(self.reactor)
        tc = QVBoxLayout(); tc.setSpacing(2)
        t1 = QLabel("J.A.R.V.I.S")
        t1.setFont(QFont("Courier New", 20, QFont.Weight.Bold))
        t1.setStyleSheet(f"color: {J_CYAN}; letter-spacing: 6px;")
        t2 = QLabel("JUST A RATHER VERY INTELLIGENT SYSTEM")
        t2.setFont(QFont("Courier New", 8))
        t2.setStyleSheet(f"color: {J_MUTED}; letter-spacing: 3px;")
        tc.addWidget(t1); tc.addWidget(t2)
        left.addLayout(tc)
        tb.addLayout(left)
        tb.addStretch()

        wc = QVBoxLayout(); wc.setSpacing(2)
        self.waveform = WaveformWidget(); self.waveform.setFixedWidth(200)
        wl = QLabel("AUDIO INPUT STREAM")
        wl.setFont(QFont("Courier New", 7))
        wl.setStyleSheet(f"color: {J_MUTED}; letter-spacing: 2px;")
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wc.addWidget(self.waveform); wc.addWidget(wl)
        tb.addLayout(wc)
        tb.addStretch()

        rc = QVBoxLayout(); rc.setSpacing(2); rc.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.clock_lbl = QLabel(datetime.now().strftime("%H:%M:%S"))
        self.clock_lbl.setFont(QFont("Courier New", 18, QFont.Weight.Bold))
        self.clock_lbl.setStyleSheet(f"color: {J_CYAN}; letter-spacing: 3px;")
        self.clock_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        dl = QLabel(datetime.now().strftime("%A, %d %B %Y").upper())
        dl.setFont(QFont("Courier New", 8))
        dl.setStyleSheet(f"color: {J_MUTED}; letter-spacing: 2px;")
        dl.setAlignment(Qt.AlignmentFlag.AlignRight)
        rc.addWidget(self.clock_lbl); rc.addWidget(dl)
        tb.addLayout(rc)
        root.addWidget(topbar)

        # ── Body ──
        body = QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)

        # Sidebar
        sidebar = QFrame()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet(f"background: {J_NAVY}; border-right: 1px solid {J_BORDER};")
        sb = QVBoxLayout(sidebar); sb.setContentsMargins(16,16,16,16); sb.setSpacing(10)

        def sec(txt):
            l = QLabel(f"// {txt}")
            l.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            l.setStyleSheet(f"color: {J_MUTED}; letter-spacing: 2px; border: none; background: transparent;")
            return l

        def divider():
            f = QFrame(); f.setFixedHeight(1)
            f.setStyleSheet(f"background: {J_BORDER}; border: none;")
            return f

        sb.addWidget(sec("SYSTEM CONTROL"))

        self.start_btn = QPushButton("▶  ACTIVATE")
        self.start_btn.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        self.start_btn.setStyleSheet(f"""
            QPushButton {{ border:1px solid {J_CYAN}; color:{J_CYAN}; background:rgba(0,212,255,0.05); padding:12px; letter-spacing:3px; }}
            QPushButton:hover {{ background:rgba(0,212,255,0.15); border-color:{J_GLOW}; color:{J_GLOW}; }}
        """)
        self.start_btn.clicked.connect(self.toggle_agent)
        sb.addWidget(self.start_btn)

        self.sleep_btn = QPushButton("⏸  STANDBY")
        self.sleep_btn.setEnabled(False)
        sb.addWidget(self.sleep_btn)

        self.clear_btn = QPushButton("⌫  CLEAR LOG")
        self.clear_btn.clicked.connect(self.clear_chat)
        sb.addWidget(self.clear_btn)

        self.mem_btn = QPushButton("◈  MEMORY CORE")
        self.mem_btn.clicked.connect(self.open_memory)
        sb.addWidget(self.mem_btn)

        sb.addWidget(divider())
        sb.addWidget(sec("AI MODEL"))
        self.model_combo = QComboBox()
        self.model_combo.addItems(["llama3.1:8b", "gemma3:4b", "mistral:7b", "gemma3:12b"])
        sb.addWidget(self.model_combo)

        sb.addWidget(divider())
        sb.addWidget(sec("VOICE SPEED"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setMinimum(100); self.speed_slider.setMaximum(250); self.speed_slider.setValue(175)
        self.speed_val = QLabel("175 WPM")
        self.speed_val.setStyleSheet(f"color: {J_CYAN}; font-size: 11px; background: transparent; border: none;")
        self.speed_slider.valueChanged.connect(lambda v: self.speed_val.setText(f"{v} WPM"))
        sb.addWidget(self.speed_slider); sb.addWidget(self.speed_val)

        sb.addStretch()
        sb.addWidget(divider())
        sb.addWidget(sec("HARDWARE"))

        gpu = QLabel("⚡ RTX 5060 LAPTOP")
        gpu.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        gpu.setStyleSheet(f"color: {J_SUCCESS}; background: transparent; border: none;")
        sb.addWidget(gpu)

        self.mem_count_lbl = QLabel("◈ 0 MEMORY ENTRIES")
        self.mem_count_lbl.setFont(QFont("Courier New", 9))
        self.mem_count_lbl.setStyleSheet(f"color: {J_MUTED}; background: transparent; border: none;")
        sb.addWidget(self.mem_count_lbl)
        body.addWidget(sidebar)

        # Chat area
        chat_c = QWidget(); chat_c.setStyleSheet(f"background: {J_BLACK};")
        chat_v = QVBoxLayout(chat_c); chat_v.setContentsMargins(0,0,0,0); chat_v.setSpacing(0)

        # Status strip
        self.status_strip = QFrame()
        self.status_strip.setFixedHeight(28)
        self.status_strip.setStyleSheet(f"background: {J_NAVY}; border-bottom: 1px solid {J_BORDER};")
        ssl = QHBoxLayout(self.status_strip); ssl.setContentsMargins(16,0,16,0)
        self.status_dot = QLabel("●"); self.status_dot.setStyleSheet(f"color: {J_MUTED}; font-size: 8px;")
        self.status_text = QLabel("SYSTEM IDLE — CLICK ACTIVATE TO BEGIN")
        self.status_text.setFont(QFont("Courier New", 9))
        self.status_text.setStyleSheet(f"color: {J_MUTED}; letter-spacing: 2px;")
        ssl.addWidget(self.status_dot); ssl.addSpacing(6); ssl.addWidget(self.status_text); ssl.addStretch()
        chat_v.addWidget(self.status_strip)

        # Scroll
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"background: {J_BLACK}; border: none;")
        self.chat_widget = QWidget(); self.chat_widget.setStyleSheet(f"background: {J_BLACK};")
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setContentsMargins(20,16,20,16); self.chat_layout.setSpacing(8)
        self.chat_layout.addStretch()
        self.scroll.setWidget(self.chat_widget)
        chat_v.addWidget(self.scroll)

        # Input
        inp_frame = QFrame(); inp_frame.setFixedHeight(80)
        inp_frame.setStyleSheet(f"background: {J_NAVY}; border-top: 1px solid {J_BORDER};")
        inp = QHBoxLayout(inp_frame); inp.setContentsMargins(16,12,16,12); inp.setSpacing(10)
        pl = QLabel(">_"); pl.setFont(QFont("Courier New", 16, QFont.Weight.Bold))
        pl.setStyleSheet(f"color: {J_CYAN}; background: transparent; border: none;")
        inp.addWidget(pl)
        self.text_input = QTextEdit()
        self.text_input.setPlaceholderText("ENTER COMMAND OR QUERY...")
        self.text_input.setFixedHeight(54)
        self.text_input.setStyleSheet(f"""
            QTextEdit {{
                background: transparent; border: none;
                border-bottom: 1px solid {J_BLUE}; border-radius: 0px;
                padding: 8px 4px; font-size: 13px; color: {J_TEXT};
                font-family: 'Courier New', monospace;
            }}
        """)
        inp.addWidget(self.text_input)
        self.send_btn = QPushButton("EXECUTE"); self.send_btn.setFixedSize(100, 54)
        self.send_btn.setStyleSheet(f"""
            QPushButton {{ border:1px solid {J_CYAN}; color:{J_CYAN}; background:rgba(0,212,255,0.05); font-size:11px; font-weight:bold; letter-spacing:2px; border-radius:2px; }}
            QPushButton:hover {{ background:rgba(0,212,255,0.15); border-color:{J_GLOW}; color:{J_GLOW}; }}
        """)
        self.send_btn.clicked.connect(self.send_text_message)
        inp.addWidget(self.send_btn)
        chat_v.addWidget(inp_frame)
        body.addWidget(chat_c)
        root.addLayout(body)

        self._add_message("JARVIS ONLINE. ALL SYSTEMS NOMINAL.\n// Click ACTIVATE for voice mode, or type below.", "ai")

    def _connect_signals(self):
        self.add_msg_signal.connect(self._add_message)
        self.status_signal.connect(self._set_status)
        self.mem_count_signal.connect(lambda n: self.mem_count_lbl.setText(f"◈ {n} MEMORY ENTRIES"))
        self.reactor_signal.connect(lambda a, l: (
            self.reactor.set_active(a), self.reactor.set_listening(l), self.waveform.set_active(l)
        ))

    def _set_status(self, text, color):
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 8px;")
        self.status_text.setText(text.upper())
        self.status_text.setStyleSheet(f"color: {color}; letter-spacing: 2px; font-family: 'Courier New'; font-size: 9px;")

    def _add_message(self, text, sender):
        ts = datetime.now().strftime("%H:%M:%S")
        msg = JarvisMessage(text, sender, ts)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, msg)
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))

    def toggle_agent(self):
        if not self.agent_running:
            self.agent_running = True
            self.start_btn.setText("⏹  DEACTIVATE")
            self.start_btn.setStyleSheet(f"""
                QPushButton {{ border:1px solid {J_RED}; color:{J_RED}; background:rgba(255,34,68,0.05); padding:12px; letter-spacing:3px; }}
                QPushButton:hover {{ background:rgba(255,34,68,0.15); }}
            """)
            self.sleep_btn.setEnabled(True)
            self.reactor.set_active(True)
            self._set_status("VOICE AGENT ACTIVE — SAY 'HEY JARVIS'", J_CYAN)
            self._add_message("// Voice agent activated. Say 'Hey Jarvis' to issue commands.", "ai")
            threading.Thread(target=self._run_agent, daemon=True).start()
        else:
            self.agent_running = False
            self.start_btn.setText("▶  ACTIVATE")
            self.start_btn.setStyleSheet(f"""
                QPushButton {{ border:1px solid {J_CYAN}; color:{J_CYAN}; background:rgba(0,212,255,0.05); padding:12px; letter-spacing:3px; }}
                QPushButton:hover {{ background:rgba(0,212,255,0.15); }}
            """)
            self.sleep_btn.setEnabled(False)
            self.reactor.set_active(False)
            self._set_status("SYSTEM IDLE", J_MUTED)
            self._add_message("// Voice agent deactivated.", "ai")

    def send_text_message(self):
        text = self.text_input.toPlainText().strip()
        if not text: return
        self.text_input.clear()
        self._add_message(text, "user")
        self._set_status("PROCESSING QUERY...", J_GOLD)
        threading.Thread(target=self._process_text, args=(text,), daemon=True).start()

    def _process_text(self, text):
        try:
            import ollama
            resp = ollama.chat(model=self.model_combo.currentText(), messages=[
                {"role":"system","content":"You are J.A.R.V.I.S, Tony Stark's AI, now serving Priyansh. Be helpful, slightly witty, and concise."},
                {"role":"user","content":text}
            ])
            reply = resp['message']['content']
            self.add_msg_signal.emit(reply, "ai")
            self.status_signal.emit("STANDBY — READY FOR INPUT", J_CYAN)
            threading.Thread(target=self._save_mem, args=(text, reply), daemon=True).start()
            self._update_memory_count()
        except Exception as ex:
            self.add_msg_signal.emit(f"// ERROR: {ex}\n// Ensure Ollama is running: ollama serve", "ai")
            self.status_signal.emit("ERROR — OLLAMA OFFLINE", J_RED)

    def _save_mem(self, user_input, ai_response):
        try:
            import chromadb
            from sentence_transformers import SentenceTransformer
            client = chromadb.PersistentClient(path="memory")
            col = client.get_or_create_collection("agent_memory")
            model = SentenceTransformer('all-MiniLM-L6-v2', local_files_only=True)
            text = f"User: {user_input} | AI: {ai_response}"
            col.add(documents=[text], embeddings=[model.encode(text).tolist()], ids=[datetime.now().isoformat()])
        except: pass

    def _update_memory_count(self):
        try:
            import chromadb
            client = chromadb.PersistentClient(path="memory")
            col = client.get_or_create_collection("agent_memory")
            self.mem_count_signal.emit(col.count())
        except: pass

    def _run_agent(self):
        try:
            import sounddevice as sd, numpy as np, tempfile, wave
            from faster_whisper import WhisperModel
            from openwakeword.model import Model as WakeWordModel
            import ollama, pyttsx3, subprocess, webbrowser, glob, urllib.parse, pyautogui

            engine = pyttsx3.init()
            engine.setProperty('rate', self.speed_slider.value())

            def speak(text):
                self.add_msg_signal.emit(text, "ai")
                engine.say(text); engine.runAndWait()

            self.status_signal.emit("LOADING WHISPER ENGINE...", J_GOLD)
            whisper_model = WhisperModel(
                r"C:\Users\priyansh\.cache\huggingface\hub\models--Systran--faster-whisper-large-v3",
                device="cuda", compute_type="float16"
            )
            self.status_signal.emit("LOADING WAKE WORD MODULE...", J_GOLD)
            wake_model = WakeWordModel(wakeword_models=["hey_jarvis"], inference_framework="tflite")
            self.status_signal.emit("ALL SYSTEMS ONLINE — AWAITING WAKE WORD", J_CYAN)

            def listen():
                SR, CHUNK = 16000, 1024
                frames, silent, speaking = [], 0, False
                max_sil = int(1.5 * SR / CHUNK)
                self.reactor_signal.emit(True, True)
                with sd.InputStream(samplerate=SR, channels=1, dtype='int16', blocksize=CHUNK) as s:
                    for _ in range(int(10 * SR / CHUNK)):
                        if not self.agent_running: return ""
                        data, _ = s.read(CHUNK); frames.append(data.copy())
                        vol = np.abs(data).mean()
                        if vol > 500: speaking = True; silent = 0
                        elif speaking:
                            silent += 1
                            if silent > max_sil: break
                self.reactor_signal.emit(True, False)
                if not speaking: return ""
                audio = np.concatenate(frames, axis=0)
                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                with wave.open(tmp.name,'wb') as wf:
                    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR); wf.writeframes(audio.tobytes())
                segs, _ = whisper_model.transcribe(tmp.name, beam_size=5, language="en", task="transcribe", condition_on_previous_text=False)
                text = " ".join([s.text for s in segs]).strip()
                try: os.remove(tmp.name)
                except: pass
                if text:
                    self.add_msg_signal.emit(text, "user")
                    self.status_signal.emit(f"PROCESSING: {text[:50]}...", J_GOLD)
                return text

            def wait_wake():
                SR, CHUNK = 16000, 1280
                with sd.InputStream(samplerate=SR, channels=1, dtype='int16', blocksize=CHUNK) as s:
                    while self.agent_running:
                        data, _ = s.read(CHUNK)
                        preds = wake_model.predict(np.frombuffer(bytes(data), dtype=np.int16))
                        for k, v in preds.items():
                            if v > 0.3: return True
                return False

            def ask_ai(prompt):
                try:
                    r = ollama.chat(model=self.model_combo.currentText(), messages=[
                        {"role":"system","content":"You are J.A.R.V.I.S serving Priyansh. Be concise and slightly witty."},
                        {"role":"user","content":prompt}
                    ])
                    return r['message']['content']
                except: return "Apologies, I encountered a system error."

            def handle_command(text):
                tl = text.lower()
                if any(x in tl for x in ["go to","navigate to","visit"]):
                    url = tl
                    for p in ["go to","navigate to","visit"]: url = url.replace(p,"")
                    url = url.strip()
                    if not url.startswith("http"): url = "https://"+url
                    webbrowser.open(url); speak(f"Navigating to {url}."); return True
                if "search youtube for" in tl or "youtube search" in tl:
                    q = tl.replace("search youtube for","").replace("youtube search","").strip()
                    webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}")
                    speak(f"Searching YouTube for {q}."); return True
                if "open youtube" in tl:
                    webbrowser.open("https://www.youtube.com"); speak("Opening YouTube."); return True
                if any(x in tl for x in ["search for","search google for","look up"]):
                    q = tl
                    for p in ["search google for","search for","look up"]: q = q.replace(p,"")
                    webbrowser.open(f"https://www.google.com/search?q={urllib.parse.quote(q.strip())}")
                    speak(f"Searching for {q.strip()}."); return True
                if "open" in tl and "in browser" in tl:
                    site = tl.replace("open","").replace("in browser","").strip()
                    webbrowser.open(f"https://www.{site}.com"); speak(f"Opening {site}."); return True
                if tl.startswith("open "):
                    app = tl.replace("open ","").strip()
                    builtin = {"notepad":"notepad.exe","calculator":"calc.exe","calc":"calc.exe",
                               "file explorer":"explorer.exe","explorer":"explorer.exe","this pc":"explorer.exe",
                               "task manager":"taskmgr.exe","settings":"ms-settings:","paint":"mspaint.exe",
                               "cmd":"cmd.exe","terminal":"wt.exe"}
                    if app in builtin:
                        subprocess.Popen(builtin[app], shell=True); speak(f"Opening {app}."); return True
                    speak(f"Searching for {app}.")
                    for d in [r"C:\Program Files",r"C:\Program Files (x86)",
                               rf"C:\Users\priyansh\AppData\Local",
                               rf"C:\Users\priyansh\AppData\Roaming",
                               rf"C:\Users\priyansh\AppData\Local\Programs"]:
                        res = glob.glob(os.path.join(d,"**",f"*{app}*.exe"),recursive=True)
                        if res: subprocess.Popen(min(res,key=len)); speak(f"Launching {app}."); return True
                    speak(f"Could not locate {app}."); return True
                if "screenshot" in tl:
                    pyautogui.screenshot().save("screenshot.png"); speak("Screenshot captured."); return True
                if "volume up" in tl:
                    [pyautogui.press("volumeup") for _ in range(5)]; speak("Volume increased."); return True
                if "volume down" in tl:
                    [pyautogui.press("volumedown") for _ in range(5)]; speak("Volume decreased."); return True
                if "mute" in tl:
                    pyautogui.press("volumemute"); speak("Audio muted."); return True
                if "shutdown pc" in tl:
                    speak("Initiating shutdown in 10 seconds."); os.system("shutdown /s /t 10"); return True
                if "restart pc" in tl:
                    speak("Restarting in 10 seconds."); os.system("shutdown /r /t 10"); return True
                if "lock pc" in tl:
                    os.system("rundll32.exe user32.dll,LockWorkStation"); speak("Workstation locked."); return True
                return False

            while self.agent_running:
                if not wait_wake(): break
                self.reactor_signal.emit(True, True)
                speak("Yes, sir?")
                self.reactor_signal.emit(True, False)
                last_cmd = ""
                while self.agent_running:
                    user_input = listen()
                    if not user_input: break
                    if any(w in user_input.lower() for w in ["sleep","standby","pause"]):
                        speak("Going to standby."); break
                    if any(w in user_input.lower() for w in ["exit","goodbye","power down","shutdown agent"]):
                        speak("Powering down. Goodbye, sir."); self.agent_running = False; break
                    if "youtube" in last_cmd and not handle_command(user_input):
                        webbrowser.open(f"https://www.youtube.com/results?search_query={urllib.parse.quote(user_input)}")
                        speak(f"Searching YouTube for {user_input}."); last_cmd = ""; continue
                    last_cmd = user_input.lower()
                    if handle_command(user_input):
                        self.status_signal.emit("ONLINE — AWAITING COMMAND", J_CYAN)
                        self._update_memory_count(); continue
                    reply = ask_ai(user_input)
                    if reply:
                        speak(reply)
                        threading.Thread(target=self._save_mem, args=(user_input, reply), daemon=True).start()
                        self._update_memory_count()
                    self.status_signal.emit("ONLINE — AWAITING COMMAND", J_CYAN)

        except Exception as ex:
            self.status_signal.emit("CRITICAL ERROR", J_RED)
            self.add_msg_signal.emit(f"// SYSTEM ERROR: {ex}", "ai")

    def clear_chat(self):
        while self.chat_layout.count() > 1:
            item = self.chat_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def open_memory(self):
        d = MemoryDialog(self); d.exec()
        self._update_memory_count()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("J.A.R.V.I.S")
    w = JarvisWindow()
    w.show()
    sys.exit(app.exec())