"""System-wide hotkey on Windows (RegisterHotKey), delivered as a Qt signal."""
from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from PyQt6.QtCore import QThread, pyqtSignal

log = logging.getLogger("jarvis.hotkey")

MODS = {"alt": 0x1, "ctrl": 0x2, "control": 0x2, "shift": 0x4, "win": 0x8}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
NAMED_KEYS = {"space": 0x20, "enter": 0x0D, "tab": 0x09, "esc": 0x1B, "backquote": 0xC0, "`": 0xC0}


def parse(combo: str) -> tuple[int, int]:
    """'ctrl+alt+j' -> (modifier flags, virtual key)."""
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("empty hotkey")
    *mods, key = parts
    flags = 0
    for m in mods:
        if m not in MODS:
            raise ValueError(f"unknown modifier '{m}'")
        flags |= MODS[m]
    if key in NAMED_KEYS:
        vk = NAMED_KEYS[key]
    elif len(key) == 1 and key.isalnum():
        vk = ord(key.upper())
    elif key.startswith("f") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    else:
        raise ValueError(f"unknown key '{key}'")
    return flags | MOD_NOREPEAT, vk


class GlobalHotkey(QThread):
    pressed = pyqtSignal()

    _next_id = 1

    def __init__(self, combo: str) -> None:
        super().__init__()
        self.combo = combo
        self.hotkey_id = GlobalHotkey._next_id
        GlobalHotkey._next_id += 1
        self._thread_id = 0

    def run(self) -> None:
        if sys.platform != "win32":
            log.info("global hotkey is Windows only")
            return
        user32 = ctypes.windll.user32
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        try:
            mods, vk = parse(self.combo)
        except ValueError as e:
            log.error("bad hotkey '%s': %s", self.combo, e)
            return
        if not user32.RegisterHotKey(None, self.hotkey_id, mods, vk):
            log.error("hotkey %s is already used by another app; change it in settings.yaml", self.combo)
            return
        log.info("hotkey registered: %s", self.combo)
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                self.pressed.emit()
        user32.UnregisterHotKey(None, self.hotkey_id)

    def stop(self) -> None:
        if self._thread_id:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        self.wait(1000)
