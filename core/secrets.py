"""API keys stored in the OS keychain (Windows Credential Manager), never in files.

Usage:
    python -m core.secrets set groq
    python -m core.secrets list
    python -m core.secrets delete groq
"""
from __future__ import annotations

import getpass
import sys

import keyring
from keyring.errors import PasswordDeleteError

SERVICE = "jarvis"
KNOWN = ("groq", "anthropic")


def get_secret(name: str) -> str | None:
    return keyring.get_password(SERVICE, name)


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def _usage() -> int:
    print(__doc__)
    return 1


def main(argv: list[str]) -> int:
    if not argv:
        return _usage()
    cmd, *rest = argv

    if cmd == "list":
        for name in KNOWN:
            print(f"{name:<10} {'set' if has_secret(name) else 'missing'}")
        return 0

    if cmd in ("set", "delete") and len(rest) == 1:
        name = rest[0].lower()
        if cmd == "set":
            value = getpass.getpass(f"{name} key (input hidden): ").strip()
            if not value:
                print("Empty value, nothing saved.")
                return 1
            keyring.set_password(SERVICE, name, value)
            print(f"Saved {name}.")
        else:
            try:
                keyring.delete_password(SERVICE, name)
                print(f"Deleted {name}.")
            except PasswordDeleteError:
                print(f"No {name} key stored.")
        return 0

    return _usage()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
