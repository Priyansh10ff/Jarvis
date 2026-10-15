"""API keys from the .env file in the project root (gitignored, never committed).

    GROQ_API_KEY=gsk_...
    ANTHROPIC_API_KEY=sk-ant-...

Real environment variables override .env. Check what was found:
    python -m core.secrets
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

from core.config import ROOT

ENV_FILE = ROOT / ".env"
KNOWN = ("groq", "anthropic")
ENV_VARS = {"groq": "GROQ_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
PREFIX = {"groq": "gsk_", "anthropic": "sk-ant-"}

load_dotenv(ENV_FILE, override=False)


def get_secret(name: str) -> str | None:
    var = ENV_VARS.get(name, name.upper())
    value = (os.environ.get(var) or "").strip().strip('"').strip("'")
    return value or None


def has_secret(name: str) -> bool:
    return bool(get_secret(name))


def _mask(value: str) -> str:
    return f"{value[:4]}…{value[-4:]} ({len(value)} chars)" if len(value) > 10 else "(too short)"


def main() -> int:
    print(f".env: {ENV_FILE} ({'found' if ENV_FILE.exists() else 'missing, copy .env.example to .env'})")
    for name in KNOWN:
        value = get_secret(name)
        if not value:
            print(f"{ENV_VARS[name]:<18} missing")
        elif not value.startswith(PREFIX[name]):
            print(f"{ENV_VARS[name]:<18} looks wrong (should start with {PREFIX[name]})")
        else:
            print(f"{ENV_VARS[name]:<18} set {_mask(value)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
