"""Natural messaging: "send hi to Ram" just works.

A fixed, tested recipe drives WhatsApp Desktop, instead of the model clicking
around step by step. If the contact has a number saved in settings, the official
whatsapp:// link opens the exact chat; otherwise Jarvis searches the chat list.
Sending always needs your "yes" (enforced by the security policy, not the model).
"""
from __future__ import annotations

import logging
import re
import time
import urllib.parse

from tools import winput
from tools.registry import tool

log = logging.getLogger("jarvis.tools.messaging")

_settings = None  # set by configure()


def configure(settings) -> None:
    global _settings
    _settings = settings


def _contacts() -> dict:
    raw = (_settings.get("contacts") if _settings else None) or {}
    return {str(k).lower(): (v or {}) for k, v in raw.items()}


def _lookup(contact: str) -> tuple[str, dict]:
    """Match a spoken name to a saved contact (exact, alias, or first name)."""
    q = contact.lower().strip()
    book = _contacts()
    if q in book:
        return q, book[q]
    for name, info in book.items():
        aliases = [a.lower() for a in info.get("aliases", [])]
        if q in aliases or name.split()[0] == q:
            return name, info
    return contact, {}


def _whatsapp_window():
    from tools.uia import find_window

    return find_window("whatsapp")


def _open_whatsapp() -> tuple[int, str] | None:
    from tools.system import open_app

    w = _whatsapp_window()
    if not w:
        result = open_app("WhatsApp")
        if result.startswith("Error"):
            return None
        for _ in range(30):  # up to ~6 s to start
            time.sleep(0.2)
            w = _whatsapp_window()
            if w:
                time.sleep(1.0)  # let the chat list load
                break
    if not w:
        return None
    winput.bring_to_front(w[0])
    return w[0], w[1]


def _click_search_result(hwnd: int, name: str) -> bool:
    """After searching, click the chat whose name matches (UI Automation)."""
    from tools.uia import _uia, _walk

    q = name.lower()
    with _uia() as auto:
        root = auto.ControlFromHandle(hwnd)
        best = None
        for ctrl in _walk(auto, root, budget=2.5):
            try:
                label = (ctrl.Name or "").strip().lower()
                if not label or ctrl.IsOffscreen or "search" in label:
                    continue
                if ctrl.ControlTypeName in ("ListItemControl", "ButtonControl", "DataItemControl") and label.startswith(q):
                    best = ctrl
                    break
            except Exception:
                continue
        if not best:
            return False
        try:
            best.GetInvokePattern().Invoke()
        except Exception:
            try:
                best.GetSelectionItemPattern().Select()
            except Exception:
                best.Click(simulateMove=False)
    return True


def _chat_is_open(hwnd: int) -> bool:
    """A chat is open when the message box ("Type a message") exists."""
    from tools.uia import _uia, _walk

    with _uia() as auto:
        for ctrl in _walk(auto, auto.ControlFromHandle(hwnd), budget=2.0):
            try:
                if ctrl.ControlTypeName in ("EditControl", "DocumentControl") and \
                        "type a message" in (ctrl.Name or "").lower():
                    return True
            except Exception:
                continue
    return False


@tool(
    "send_message",
    "Send a message to a person, e.g. 'send hi to Ram', 'tell Mom I'll be late', 'message Rahul on WhatsApp "
    "that the meeting moved'. Use this instead of clicking around in the app. Write the message the way the "
    "user would send it (first person, natural), not as an instruction.",
    {
        "type": "object",
        "properties": {
            "contact": {"type": "string", "description": "person's name as the user said it"},
            "text": {"type": "string", "description": "the exact message to send"},
            "app": {"type": "string", "enum": ["whatsapp"], "default": "whatsapp"},
        },
        "required": ["contact", "text"],
    },
    level="confirm",
    confirm_prompt='send "{text}" to {contact}',
)
def send_message(contact: str, text: str, app: str = "whatsapp") -> str:
    if app != "whatsapp":
        return f"Error: sending on {app} isn't supported yet, only WhatsApp."
    if not text.strip():
        return "Error: the message is empty."
    name, info = _lookup(contact)
    phone = re.sub(r"[^\d]", "", str(info.get("whatsapp") or info.get("phone") or ""))

    if phone:
        # Official deep link: opens the exact chat with the text already typed.
        from os import startfile

        startfile(f"whatsapp://send?phone={phone}&text={urllib.parse.quote(text)}")
        time.sleep(2.5)
        w = _whatsapp_window()
        if not w:
            return "Error: WhatsApp didn't open. Is WhatsApp Desktop installed?"
        winput.bring_to_front(w[0])
        time.sleep(0.3)
        winput.press_combo(["enter"])
        return f"Sent to {name.title()} on WhatsApp."

    opened = _open_whatsapp()
    if not opened:
        return "Error: WhatsApp Desktop isn't installed or didn't open. Install it from the Microsoft Store."
    hwnd, _title = opened

    # Search the chat list and open the chat.
    winput.press_combo(["esc"])
    winput.press_combo(["ctrl", "f"])
    time.sleep(0.4)
    winput.press_combo(["ctrl", "a"])
    winput.type_unicode(contact)
    time.sleep(1.2)
    if not _click_search_result(hwnd, contact):
        winput.press_combo(["down"])
        time.sleep(0.2)
        winput.press_combo(["enter"])
    time.sleep(0.8)

    if not _chat_is_open(hwnd):
        winput.press_combo(["esc"])
        return f"Error: couldn't find a chat named {contact} in WhatsApp. Nothing was sent."

    winput.type_unicode(text)
    time.sleep(0.2)
    winput.press_combo(["enter"])
    log.info("sent WhatsApp message to %s", contact)
    return f"Sent to {contact.title()} on WhatsApp."
