"""Entry point: python -m core.main"""
from __future__ import annotations

import logging
from pathlib import Path

from core.config import ROOT, load_settings
from core.secrets import KNOWN, has_secret

log = logging.getLogger("jarvis")


def setup_logging(level: str, file: str) -> None:
    log_path = ROOT / file
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_path, encoding="utf-8")],
    )


def main() -> None:
    settings = load_settings()
    setup_logging(settings.get("logging.level", "INFO"), settings.get("logging.file", "logs/jarvis.log"))

    for name in KNOWN:
        log.info("key %-10s %s", name, "ok" if has_secret(name) else "missing")

    log.info("%s core online for %s", settings.assistant_name, settings.user_name)


if __name__ == "__main__":
    main()
