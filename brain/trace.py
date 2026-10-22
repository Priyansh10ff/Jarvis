"""One line per request in logs/traces.jsonl: what was heard, which model, what it
did, what it said, how long it took. Say "that was wrong" to flag the last one.

This is how bad answers get fixed: flagged traces show exactly what went wrong.
    python -m brain.trace           show the last 20
    python -m brain.trace --flagged show only flagged ones
"""
from __future__ import annotations

import json
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from core.config import ROOT
from security.redact import redact, redact_value

PATH = ROOT / "logs" / "traces.jsonl"
_lock = threading.Lock()


def write(entry: dict[str, Any]) -> None:
    entry = {"time": datetime.now().isoformat(timespec="seconds"), **entry}
    entry = redact_value(entry)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def flag_last(note: str = "") -> bool:
    """Mark the most recent request as wrong (rewrites the last line)."""
    with _lock:
        if not PATH.exists():
            return False
        lines = PATH.read_text(encoding="utf-8").splitlines()
        if not lines:
            return False
        last = json.loads(lines[-1])
        last["flagged"] = True
        if note:
            last["flag_note"] = redact(note)
        lines[-1] = json.dumps(last, ensure_ascii=False)
        PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return True


def _show(flagged_only: bool) -> None:
    if not PATH.exists():
        print("No traces yet.")
        return
    rows = [json.loads(l) for l in PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    if flagged_only:
        rows = [r for r in rows if r.get("flagged")]
    for r in rows[-20:]:
        mark = "  [WRONG]" if r.get("flagged") else ""
        print(f"\n{r['time']}  {r.get('source', '')}  {r.get('model', '')}  {r.get('ms', '')} ms{mark}")
        print(f"  you:    {r.get('text', '')}")
        for a in r.get("actions", []):
            print(f"  did:    {a}")
        print(f"  jarvis: {r.get('reply', '')}")


if __name__ == "__main__":
    _show("--flagged" in sys.argv)
