"""Windows PC tools: apps, web, media keys, volume, screenshots, lock, power, status."""
from __future__ import annotations

import ctypes
import difflib
import json
import logging
import os
import re
import subprocess
import sys
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path

from tools.registry import tool

log = logging.getLogger("jarvis.tools.system")

IS_WINDOWS = sys.platform == "win32"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0  # CREATE_NO_WINDOW


# ── Apps ──────────────────────────────────────────────────────────────────────

BUILTIN = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "file explorer": "explorer.exe",
    "explorer": "explorer.exe",
    "task manager": "taskmgr.exe",
    "settings": "ms-settings:",
    "paint": "mspaint.exe",
    "command prompt": "cmd.exe",
    "cmd": "cmd.exe",
    "terminal": "wt.exe",
    "powershell": "powershell.exe",
    "control panel": "control.exe",
}

_apps_cache: dict[str, str] | None = None


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def installed_apps() -> dict[str, str]:
    """Start-menu apps (desktop + Store) as {normalized name: AppID}, cached."""
    global _apps_cache
    if _apps_cache is not None:
        return _apps_cache
    _apps_cache = {}
    if not IS_WINDOWS:
        return _apps_cache
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW,
        ).stdout
        items = json.loads(out or "[]")
        if isinstance(items, dict):
            items = [items]
        for item in items:
            _apps_cache[_norm(item["Name"])] = item["AppID"]
        log.info("indexed %d start-menu apps", len(_apps_cache))
    except Exception:
        log.exception("could not list start-menu apps")
    return _apps_cache


def find_app(name: str) -> tuple[str, str] | None:
    """Return (display name, AppID) for the best match."""
    apps = installed_apps()
    q = _norm(name)
    if not q or not apps:
        return None
    if q in apps:
        return q, apps[q]
    starts = [n for n in apps if n.startswith(q)]
    if starts:
        best = min(starts, key=len)
        return best, apps[best]
    contains = [n for n in apps if q in n]
    if contains:
        best = min(contains, key=len)
        return best, apps[best]
    close = difflib.get_close_matches(q, list(apps), n=1, cutoff=0.6)
    return (close[0], apps[close[0]]) if close else None


@tool(
    "open_app",
    "Open an installed application by name, e.g. Spotify, Chrome, VS Code, Notepad, Settings.",
    {"type": "object", "properties": {"name": {"type": "string", "description": "App name as the user said it"}}, "required": ["name"]},
)
def open_app(name: str) -> str:
    if not IS_WINDOWS:
        return "Error: only supported on Windows"
    key = _norm(name)
    if key in BUILTIN:
        os.startfile(BUILTIN[key])
        return f"Opened {name}"
    match = find_app(name)
    if not match:
        return f"Error: no installed app matches '{name}'"
    display, app_id = match
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app_id}"], creationflags=NO_WINDOW)
    return f"Opened {display}"


# ── Web ───────────────────────────────────────────────────────────────────────

@tool(
    "open_website",
    "Open a website in the default browser, e.g. github.com or amazon.in.",
    {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
)
def open_website(url: str) -> str:
    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https") or "." not in parsed.netloc:
        return f"Error: '{url}' is not a valid web address"
    webbrowser.open(url)
    return f"Opened {parsed.netloc}"


@tool(
    "web_search",
    "Search the web in the browser. Use site=youtube for videos or music.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "site": {"type": "string", "enum": ["google", "youtube"], "default": "google"},
        },
        "required": ["query"],
    },
)
def web_search(query: str, site: str = "google") -> str:
    q = urllib.parse.quote_plus(query)
    if site == "youtube":
        webbrowser.open(f"https://www.youtube.com/results?search_query={q}")
    else:
        webbrowser.open(f"https://www.google.com/search?q={q}")
    return f"Searched {site} for {query}"


# ── Media and volume (virtual keys, no extra libraries) ──────────────────────

VK = {"volume_up": 0xAF, "volume_down": 0xAE, "mute": 0xAD, "play_pause": 0xB3, "next": 0xB0, "previous": 0xB1}


def _press(vk: int, times: int = 1) -> None:
    for _ in range(times):
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)  # key up


@tool(
    "volume",
    "Change system volume. Each step is about 2 percent.",
    {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["up", "down", "mute"]},
            "steps": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
        },
        "required": ["action"],
    },
)
def volume(action: str, steps: int = 5) -> str:
    if not IS_WINDOWS:
        return "Error: only supported on Windows"
    if action == "mute":
        _press(VK["mute"])
        return "Toggled mute"
    _press(VK["volume_up" if action == "up" else "volume_down"], max(1, min(50, steps)))
    return f"Volume {action} {steps} steps"


@tool(
    "media",
    "Control whatever media is playing (Spotify, YouTube, etc.).",
    {"type": "object", "properties": {"action": {"type": "string", "enum": ["play_pause", "next", "previous"]}}, "required": ["action"]},
)
def media(action: str) -> str:
    if not IS_WINDOWS:
        return "Error: only supported on Windows"
    _press(VK[action])
    return f"Media {action.replace('_', '/')}"


# ── Screen, lock, power, status ──────────────────────────────────────────────

@tool("screenshot", "Take a screenshot and save it to Pictures/Jarvis.")
def screenshot() -> str:
    from PIL import ImageGrab

    folder = Path.home() / "Pictures" / "Jarvis"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"screenshot-{datetime.now():%Y%m%d-%H%M%S}.png"
    ImageGrab.grab(all_screens=True).save(path)
    return f"Saved screenshot to {path}"


@tool("lock_pc", "Lock the computer.")
def lock_pc() -> str:
    if not IS_WINDOWS:
        return "Error: only supported on Windows"
    ctypes.windll.user32.LockWorkStation()
    return "Locked the PC"


@tool(
    "power",
    "Shut down, restart or put the PC to sleep.",
    {"type": "object", "properties": {"action": {"type": "string", "enum": ["shutdown", "restart", "sleep"]}}, "required": ["action"]},
    level="confirm",
    confirm_prompt="{action} the PC",
)
def power(action: str) -> str:
    if not IS_WINDOWS:
        return "Error: only supported on Windows"
    if action == "shutdown":
        subprocess.run(["shutdown", "/s", "/t", "10"], creationflags=NO_WINDOW)
        return "Shutting down in 10 seconds"
    if action == "restart":
        subprocess.run(["shutdown", "/r", "/t", "10"], creationflags=NO_WINDOW)
        return "Restarting in 10 seconds"
    ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
    return "Going to sleep"


@tool("system_status", "Get battery, CPU and memory usage.")
def system_status() -> str:
    import psutil

    parts = [f"CPU {psutil.cpu_percent(interval=0.3):.0f}%", f"RAM {psutil.virtual_memory().percent:.0f}%"]
    battery = psutil.sensors_battery()
    if battery:
        parts.append(f"battery {battery.percent:.0f}%{' charging' if battery.power_plugged else ''}")
    return ", ".join(parts)
