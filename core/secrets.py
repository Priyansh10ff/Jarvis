"""API keys stored in the OS keychain (Windows Credential Manager), never in files.

Usage:
    python -m core.secrets set groq --paste   (copy the key first; reads your clipboard)
    python -m core.secrets set groq           (type or paste at a hidden prompt)
    python -m core.secrets list
    python -m core.secrets delete groq
"""
from __future__ import annotations

import getpass
import subprocess
import sys

import keyring
from keyring.errors import PasswordDeleteError

SERVICE = "jarvis"
KNOWN = ("groq", "anthropic")
PREFIX = {"groq": "gsk_", "anthropic": "sk-ant-"}


def get_secret(name: str) -> str | None:
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:  # no keychain backend available
        return None


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def _mask(value: str) -> str:
    return f"{value[:4]}…{value[-4:]} ({len(value)} chars)" if len(value) > 10 else "(too short)"


def _clipboard() -> str:
    if sys.platform == "win32":
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
            capture_output=True, text=True, timeout=10,
        )
        return out.stdout
    raise RuntimeError("--paste is Windows only; use the hidden prompt")


def _set(name: str, paste: bool) -> int:
    if paste:
        value = _clipboard()
    else:
        print("Tip: if pasting here does nothing, copy the key and use --paste instead.")
        value = getpass.getpass(f"{name} key (input hidden): ")
    value = "".join(value.split())  # drop spaces/newlines picked up by copy-paste

    if not value:
        print("Empty value, nothing saved.")
        return 1
    expected = PREFIX.get(name)
    if expected and not value.startswith(expected):
        print(f"That doesn't look like a {name} key (should start with {expected}). Nothing saved.")
        return 1

    keyring.set_password(SERVICE, name, value)
    stored = get_secret(name)
    if stored != value:
        print("Saving failed: the keychain did not return the key. Nothing usable was stored.")
        return 1
    print(f"Saved {name}: {_mask(value)}")
    return 0


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, *rest = argv
    paste = "--paste" in rest
    rest = [r for r in rest if r != "--paste"]

    if cmd == "list":
        try:
            backend = keyring.get_keyring().__class__.__name__
        except Exception as e:
            print(f"No keychain available: {e}")
            return 1
        print(f"keychain: {backend}")
        for name in KNOWN:
            value = get_secret(name)
            print(f"{name:<10} {'set ' + _mask(value) if value else 'missing'}")
        return 0

    if cmd == "set" and len(rest) == 1:
        return _set(rest[0].lower(), paste)

    if cmd == "delete" and len(rest) == 1:
        name = rest[0].lower()
        try:
            keyring.delete_password(SERVICE, name)
            print(f"Deleted {name}.")
        except PasswordDeleteError:
            print(f"No {name} key stored.")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
