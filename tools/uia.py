"""App control: switch windows, type, press keys, click buttons by name, read a window.

Layer 2 of "control everything": apps are driven through Windows UI Automation
(their real buttons and fields), not screen pixels, so it is fast and exact.
Every action reports which window is in front afterwards, so the model can check
the step worked before the next one.
"""
from __future__ import annotations

import difflib
import logging
import time
from contextlib import contextmanager

from tools import winput
from tools.registry import tool

log = logging.getLogger("jarvis.tools.uia")

CLICKABLE = {"ButtonControl", "ListItemControl", "MenuItemControl", "HyperlinkControl", "TabItemControl",
             "TreeItemControl", "CheckBoxControl", "RadioButtonControl", "SplitButtonControl", "TextControl"}
READABLE = {"TextControl", "EditControl", "DocumentControl", "ListItemControl", "HyperlinkControl",
            "ButtonControl", "TabItemControl", "TreeItemControl", "HeaderItemControl", "DataItemControl"}


@contextmanager
def _uia():
    """UI Automation is COM: each thread must initialise it."""
    import uiautomation as auto

    with auto.UIAutomationInitializerInThread():
        yield auto


def _process_name(pid: int) -> str:
    try:
        import psutil

        return psutil.Process(pid).name().rsplit(".", 1)[0]
    except Exception:
        return ""


def _windows() -> list[tuple[int, str, str]]:
    """(hwnd, title, process) for every normal window, front first."""
    return [(h, winput.window_title(h), _process_name(winput.window_pid(h))) for h in winput.top_windows()]


def find_window(query: str | None) -> tuple[int, str, str] | None:
    """Best window for a spoken name ("vs code", "chrome", "claude"); None = the front window."""
    wins = _windows()
    if not query:
        fg = winput.foreground_hwnd()
        for w in wins:
            if w[0] == fg:
                return w
        return wins[0] if wins else None
    q = query.lower().replace("vs code", "visual studio code").strip()
    for match in (
        lambda w: q == w[2].lower() or q == w[1].lower(),
        lambda w: q in w[1].lower(),
        lambda w: q in w[2].lower() or w[2].lower() in q.replace(" ", ""),
    ):
        hits = [w for w in wins if w[2] and match(w)] or [w for w in wins if match(w)]
        if hits:
            return hits[0]
    titles = {w[1].lower(): w for w in wins}
    close = difflib.get_close_matches(q, list(titles), n=1, cutoff=0.5)
    return titles[close[0]] if close else None


def target_title(window: str | None) -> str:
    """Title + process of the window an action would touch (used by the security policy)."""
    w = find_window(window)
    return f"{w[1]} [{w[2]}]" if w else ""


def _front_note() -> str:
    hwnd = winput.foreground_hwnd()
    return f"Now in front: {winput.window_title(hwnd) or 'desktop'}"


def _focus(window: str | None) -> tuple[int, str] | str:
    w = find_window(window)
    if not w:
        return f"Error: no open window matches '{window}'. Open the app first."
    if window:
        winput.bring_to_front(w[0])
    return w[0], w[1]


# ── tools ────────────────────────────────────────────────────────────────────

@tool("list_windows", "List the open windows (title and app). Use it to find the right window name.", final=False)
def list_windows() -> str:
    wins = _windows()[:20]
    if not wins:
        return "No open windows."
    return "Open windows: " + "; ".join(f"{t} ({p})" if p else t for _, t, p in wins)


@tool(
    "focus_window",
    "Bring an open window to the front by app or title, e.g. 'VS Code', 'Chrome', 'Claude', 'Spotify'.",
    {"type": "object", "properties": {"window": {"type": "string"}}, "required": ["window"]},
)
def focus_window(window: str) -> str:
    w = find_window(window)
    if not w:
        return f"Error: no open window matches '{window}'. Open the app first."
    ok = winput.bring_to_front(w[0])
    return f"Switched to {w[1]}" if ok else f"Error: Windows didn't let me bring '{w[1]}' to the front. {_front_note()}"


@tool(
    "window_action",
    "Minimize, maximize, restore or close an open window.",
    {
        "type": "object",
        "properties": {
            "window": {"type": "string"},
            "action": {"type": "string", "enum": ["minimize", "maximize", "restore", "close"]},
        },
        "required": ["window", "action"],
    },
)
def window_action(window: str, action: str) -> str:
    w = find_window(window)
    if not w:
        return f"Error: no open window matches '{window}'"
    if action == "close":
        winput.close(w[0])  # the app still asks to save unsaved work
        return f"Closed {w[1]}"
    winput.show(w[0], {"minimize": winput.SW_MINIMIZE, "maximize": winput.SW_MAXIMIZE, "restore": winput.SW_RESTORE}[action])
    return f"{action.capitalize()}d {w[1]}"


@tool(
    "type_text",
    "Type text into a window (the front window if none given), where the cursor is. Does not press Enter.",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "window": {"type": "string", "description": "optional app/window to type into"},
        },
        "required": ["text"],
    },
)
def type_text(text: str, window: str | None = None) -> str:
    target = _focus(window)
    if isinstance(target, str):
        return target
    winput.type_unicode(text)
    return f"Typed {len(text)} characters into {target[1]}"


@tool(
    "press_keys",
    "Press a key or shortcut in a window (the front window if none given), e.g. 'enter', 'ctrl+s', 'ctrl+t', 'alt+tab'.",
    {
        "type": "object",
        "properties": {"keys": {"type": "string"}, "window": {"type": "string"}},
        "required": ["keys"],
    },
)
def press_keys(keys: str, window: str | None = None) -> str:
    try:
        parts = winput.parse_combo(keys)
    except ValueError as e:
        return f"Error: {e}"
    target = _focus(window)
    if isinstance(target, str):
        return target
    winput.press_combo(parts)
    time.sleep(0.2)
    return f"Pressed {'+'.join(parts)}. {_front_note()}"


def _walk(auto, root, max_depth: int = 30, budget: float = 3.0, limit: int = 5000):
    deadline = time.monotonic() + budget
    for count, (ctrl, _depth) in enumerate(auto.WalkControl(root, includeTop=False, maxDepth=max_depth)):
        if count >= limit or time.monotonic() > deadline:
            return
        yield ctrl


def _window_control(auto, hwnd: int):
    return auto.ControlFromHandle(hwnd)


@tool(
    "click_element",
    "Click a button, tab, link, menu item or list item by its visible name in a window "
    "(the front window if none given), e.g. 'New chat', 'Settings', a chat or file name.",
    {
        "type": "object",
        "properties": {"name": {"type": "string"}, "window": {"type": "string"}},
        "required": ["name"],
    },
)
def click_element(name: str, window: str | None = None) -> str:
    target = _focus(window)
    if isinstance(target, str):
        return target
    hwnd, title = target
    q = name.lower().strip()
    with _uia() as auto:
        root = _window_control(auto, hwnd)
        exact, partial = None, None
        for ctrl in _walk(auto, root):
            try:
                label = (ctrl.Name or "").strip()
                if not label or ctrl.IsOffscreen:
                    continue
                low = label.lower()
                rank = 0 if ctrl.ControlTypeName in CLICKABLE else 1
                if low == q and (exact is None or rank < exact[0]):
                    exact = (rank, ctrl)
                    if rank == 0:
                        break
                elif q in low and partial is None:
                    partial = (rank, ctrl)
            except Exception:
                continue
        hit = (exact or partial)
        if not hit:
            return (f"Error: no element named '{name}' found in {title}. "
                    "Try read_window to see what is there, or click_on_screen to find it visually.")
        ctrl = hit[1]
        label = ctrl.Name
        for pattern in ("GetInvokePattern", "GetSelectionItemPattern", "GetTogglePattern"):
            try:
                p = getattr(ctrl, pattern)()
                if p:
                    {"GetInvokePattern": lambda: p.Invoke(), "GetSelectionItemPattern": lambda: p.Select(),
                     "GetTogglePattern": lambda: p.Toggle()}[pattern]()
                    break
            except Exception:
                continue
        else:
            ctrl.Click(simulateMove=False, waitTime=0.1)
    time.sleep(0.3)
    return f"Clicked '{label}' in {title}. {_front_note()}"


@tool(
    "read_window",
    "Read the visible text of a window (the front window if none given): labels, messages, fields. "
    "Use it to answer questions about what is on screen or to find what to click.",
    {"type": "object", "properties": {"window": {"type": "string"}}},
    final=False,
)
def read_window(window: str | None = None) -> str:
    w = find_window(window)
    if not w:
        return f"Error: no open window matches '{window}'"
    seen: set[str] = set()
    lines: list[str] = []
    total = 0
    with _uia() as auto:
        for ctrl in _walk(auto, _window_control(auto, w[0]), budget=3.0):
            try:
                if ctrl.ControlTypeName not in READABLE or ctrl.IsOffscreen:
                    continue
                text = (ctrl.Name or "").strip()
                if ctrl.ControlTypeName in ("EditControl", "DocumentControl"):
                    try:
                        value = ctrl.GetValuePattern().Value
                        text = value or text
                    except Exception:
                        pass
                text = " ".join(text.split())
                if not text or text in seen:
                    continue
                seen.add(text)
                lines.append(text[:300])
                total += len(text)
                if total > 2500:
                    lines.append("…")
                    break
            except Exception:
                continue
    if not lines:
        return f"{w[1]}: no readable text (the app may not expose it)."
    return f"{w[1]}:\n" + "\n".join(lines)
