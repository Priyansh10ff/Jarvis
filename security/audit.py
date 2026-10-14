"""Append-only audit trail of every action Jarvis was asked to take."""
from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from security.redact import redact, redact_value

_lock = threading.Lock()
_path: Path | None = None


def configure(path: Path) -> None:
    global _path
    path.parent.mkdir(parents=True, exist_ok=True)
    _path = path


def record(tool: str, args: dict[str, Any], decision: str, result: str = "", reason: str = "") -> None:
    if _path is None:
        return
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "tool": tool,
        "args": redact_value(args),
        "decision": decision,
        "reason": reason,
        "result": redact(result)[:300],
    }
    with _lock, _path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
