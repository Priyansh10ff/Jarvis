"""Low-level Windows keyboard and window helpers (ctypes, no extra libraries).

Typing uses SendInput with Unicode events, so any character (braces, emoji,
Hindi) arrives exactly as written, independent of keyboard layout.
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
ULONG_PTR = ctypes.c_size_t


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


def _send(inputs: list[INPUT]) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    return INPUT(type=INPUT_KEYBOARD, u=_UNION(ki=KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=flags, time=0, dwExtraInfo=0)))


def type_unicode(text: str, delay: float = 0.004) -> None:
    for ch in text:
        if ch == "\n":
            press_combo(["shift", "enter"])  # new line without sending in chat apps
            continue
        for unit in _utf16_units(ch):
            _send([_key(scan=unit, flags=KEYEVENTF_UNICODE), _key(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)])
        if delay:
            time.sleep(delay)


def _utf16_units(ch: str) -> list[int]:
    data = ch.encode("utf-16-le")
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]


VK = {
    "ctrl": 0x11, "control": 0x11, "alt": 0x12, "shift": 0x10, "win": 0x5B, "windows": 0x5B,
    "enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "insert": 0x2D,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "printscreen": 0x2C, "capslock": 0x14,
}
MODIFIERS = {"ctrl", "control", "alt", "shift", "win", "windows"}


def parse_combo(combo: str) -> list[str]:
    parts = [p.strip().lower() for p in combo.replace(" ", "+").split("+") if p.strip()]
    if not parts:
        raise ValueError("no keys given")
    for p in parts:
        if not (p in VK or (len(p) == 1 and p.isalnum()) or (p.startswith("f") and p[1:].isdigit() and 1 <= int(p[1:]) <= 24)):
            raise ValueError(f"unknown key '{p}'")
    return parts


def _vk(name: str) -> int:
    if name in VK:
        return VK[name]
    if len(name) == 1 and name.isalnum():
        return ord(name.upper())
    return 0x6F + int(name[1:])  # F1..F24


def press_combo(parts: list[str]) -> None:
    """Hold modifiers, tap the other keys, release modifiers: ['ctrl','s']."""
    mods = [p for p in parts if p in MODIFIERS]
    keys = [p for p in parts if p not in MODIFIERS] or []
    events = [_key(vk=_vk(m)) for m in mods]
    for k in keys:
        events += [_key(vk=_vk(k)), _key(vk=_vk(k), flags=KEYEVENTF_KEYUP)]
    events += [_key(vk=_vk(m), flags=KEYEVENTF_KEYUP) for m in reversed(mods)]
    _send(events)


# ── windows ──────────────────────────────────────────────────────────────────

SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 6, 3, 9
WM_CLOSE = 0x0010


def foreground_hwnd() -> int:
    return user32.GetForegroundWindow() if IS_WINDOWS else 0


def window_title(hwnd: int) -> str:
    if not IS_WINDOWS or not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def bring_to_front(hwnd: int) -> bool:
    """Focus a window even though Windows normally blocks background apps from doing so."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    me = kernel32.GetCurrentThreadId()
    attached = bool(fg_thread and fg_thread != me and user32.AttachThreadInput(fg_thread, me, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(fg_thread, me, False)
    time.sleep(0.15)
    return user32.GetForegroundWindow() == hwnd


def show(hwnd: int, how: int) -> None:
    user32.ShowWindow(hwnd, how)


def close(hwnd: int) -> None:
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


def top_windows() -> list[int]:
    """Visible, titled top-level windows in z-order (front first)."""
    out: list[int] = []
    if not IS_WINDOWS:
        return out
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _lp):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            # skip tool windows (tray popups, our own overlay)
            if not (user32.GetWindowLongW(hwnd, -20) & 0x00000080):  # WS_EX_TOOLWINDOW
                out.append(hwnd)
        return True

    user32.EnumWindows(proc(cb), 0)
    return out
