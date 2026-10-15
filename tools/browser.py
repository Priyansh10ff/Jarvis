"""Browser control: Jarvis drives its own browser window (Playwright).

It uses a separate profile in data/browser-profile, so your normal Chrome/Edge
stays untouched. Log in to sites there once and Jarvis stays logged in.
Playwright objects belong to one thread, so a single worker thread owns the
browser and every tool call is handed to it.
"""
from __future__ import annotations

import logging
import queue
import re
import threading
import urllib.parse
from typing import Any, Callable

from core.config import ROOT
from tools.registry import tool

log = logging.getLogger("jarvis.tools.browser")

PROFILE = ROOT / "data" / "browser-profile"
_settings = None


def configure(settings) -> None:
    global _settings
    _settings = settings


class _Worker:
    def __init__(self) -> None:
        self._jobs: queue.Queue[tuple[Callable[[Any], Any], queue.Queue]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._pw = None
        self._ctx = None

    def _start(self) -> None:
        from playwright.sync_api import sync_playwright

        channel = (_settings.get("browser.channel") if _settings else None) or "msedge"
        PROFILE.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            str(PROFILE),
            channel=channel,           # uses the installed Edge/Chrome, no extra download
            headless=False,
            accept_downloads=False,    # nothing gets saved to disk behind your back
            no_viewport=True,
            args=["--start-maximized"],
        )
        self._ctx.set_default_timeout(8000)
        log.info("browser started (%s)", channel)

    def _page(self):
        if self._ctx is None:
            self._start()
        pages = [p for p in self._ctx.pages if not p.is_closed()]
        return pages[-1] if pages else self._ctx.new_page()

    def _loop(self) -> None:
        while True:
            fn, reply = self._jobs.get()
            try:
                try:
                    page = self._page()
                except Exception:
                    # Browser was closed by the user: start fresh.
                    self._ctx = None
                    page = self._page()
                reply.put((True, fn(page)))
            except Exception as e:
                reply.put((False, e))

    def run(self, fn: Callable[[Any], Any], timeout: float = 45) -> Any:
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(target=self._loop, name="browser", daemon=True)
            self._thread.start()
        reply: queue.Queue = queue.Queue()
        self._jobs.put((fn, reply))
        ok, value = reply.get(timeout=timeout)
        if not ok:
            raise value
        return value


_worker = _Worker()


def current_url() -> str:
    """URL of the page Jarvis's browser is on ('' if not started)."""
    if _worker._ctx is None:
        return ""
    try:
        return _worker.run(lambda page: page.url, timeout=5)
    except Exception:
        return ""


def _page_text(page, limit: int = 3500) -> str:
    try:
        text = page.inner_text("main", timeout=1500)
    except Exception:
        text = page.inner_text("body")
    text = re.sub(r"\n\s*\n+", "\n", text)
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text[:limit] + ("…" if len(text) > limit else "")


def _where(page) -> str:
    return f"[{page.title()[:80]} | {page.url[:120]}]"


# ── tools ────────────────────────────────────────────────────────────────────

@tool(
    "browse",
    "Open a website in Jarvis's own browser window to work on it (read, click, fill forms). "
    "Give a URL, or a search query to search Google.",
    {"type": "object", "properties": {"url_or_query": {"type": "string"}}, "required": ["url_or_query"]},
    final=False,
)
def browse(url_or_query: str) -> str:
    target = url_or_query.strip()
    if not re.match(r"^https?://", target, re.I):
        if re.match(r"^[\w-]+(\.[\w-]+)+(/\S*)?$", target):
            target = "https://" + target
        else:
            target = "https://www.google.com/search?q=" + urllib.parse.quote_plus(target)

    def go(page):
        page.goto(target, wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        return f"Opened {_where(page)}\n{_page_text(page, 2500)}"

    return _worker.run(go)


@tool(
    "browser_read",
    "Read the text of the page open in Jarvis's browser, to answer questions or find what to click.",
    final=False,
)
def browser_read() -> str:
    return _worker.run(lambda page: f"{_where(page)}\n{_page_text(page)}")


def _locate(page, target: str):
    """Find something to click by what it says: button, link, tab, then any text."""
    exact = re.compile(rf"^\s*{re.escape(target)}\s*$", re.I)
    loose = re.compile(re.escape(target), re.I)
    for role in ("button", "link", "tab", "menuitem", "option", "checkbox", "radio"):
        for name in (exact, loose):
            loc = page.get_by_role(role, name=name)
            if loc.count():
                return loc.first
    loc = page.get_by_text(loose)
    return loc.first if loc.count() else None


@tool(
    "browser_click",
    "Click a button, link or tab on the page in Jarvis's browser by the words on it.",
    {"type": "object", "properties": {"target": {"type": "string"}}, "required": ["target"]},
)
def browser_click(target: str) -> str:
    def click(page):
        loc = _locate(page, target)
        if loc is None:
            return f"Error: nothing that says '{target}' on this page. Use browser_read to see what's there."
        loc.click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(600)
        return f"Clicked '{target}'. Now on {_where(page)}"

    return _worker.run(click)


SENSITIVE_FIELD = re.compile(
    r"(?i)(password|passcode|pin\b|otp|one.time|cvv|cvc|card.?number|expiry|security code|ssn|aadhaar|"
    r"\bpan\b|account.?number|ifsc|upi pin)"
)


@tool(
    "browser_fill",
    "Type into a field on the page in Jarvis's browser, found by its label or placeholder "
    "(e.g. 'Search', 'Email', 'From', 'To'). Never used for passwords, card numbers or OTPs.",
    {
        "type": "object",
        "properties": {"field": {"type": "string"}, "text": {"type": "string"}},
        "required": ["field", "text"],
    },
)
def browser_fill(field: str, text: str) -> str:
    def fill(page):
        name = re.compile(re.escape(field), re.I)
        loc = None
        for finder in (
            lambda: page.get_by_label(name),
            lambda: page.get_by_placeholder(name),
            lambda: page.get_by_role("textbox", name=name),
            lambda: page.get_by_role("searchbox", name=name),
            lambda: page.get_by_role("combobox", name=name),
        ):
            candidate = finder()
            if candidate.count():
                loc = candidate.first
                break
        if loc is None:
            return f"Error: no field called '{field}' on this page."
        kind = (loc.get_attribute("type") or "").lower()
        autocomplete = (loc.get_attribute("autocomplete") or "").lower()
        if kind == "password" or "cc-" in autocomplete or "one-time-code" in autocomplete:
            return "Blocked by security policy: Jarvis never types passwords, card details or OTPs. Ask the user to type it."
        loc.fill(text)
        return f"Filled '{field}'."

    return _worker.run(fill)


@tool(
    "browser_press",
    "Press a key on the page in Jarvis's browser, e.g. 'Enter' to submit a search, 'Escape', 'PageDown'.",
    {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]},
)
def browser_press(key: str) -> str:
    keymap = {"enter": "Enter", "escape": "Escape", "esc": "Escape", "tab": "Tab", "pagedown": "PageDown",
              "pageup": "PageUp", "down": "ArrowDown", "up": "ArrowUp", "backspace": "Backspace"}
    k = keymap.get(key.lower().replace(" ", ""), key)

    def press(page):
        page.keyboard.press(k)
        page.wait_for_timeout(800)
        return f"Pressed {k}. Now on {_where(page)}"

    return _worker.run(press)


@tool("browser_back", "Go back to the previous page in Jarvis's browser.")
def browser_back() -> str:
    def back(page):
        page.go_back(wait_until="domcontentloaded")
        return f"Went back to {_where(page)}"

    return _worker.run(back)
