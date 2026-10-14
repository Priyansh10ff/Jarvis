"""Start Jarvis at Windows logon via the per-user Run key (no admin needed).

Usage:
    python -m core.autostart install
    python -m core.autostart uninstall
    python -m core.autostart status
"""
from __future__ import annotations

import sys
from pathlib import Path

from core.config import ROOT

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Jarvis"
LAUNCHER = ROOT / "jarvis.pyw"


def _pythonw() -> Path:
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def command() -> str:
    return f'"{_pythonw()}" "{LAUNCHER}"'


def _open(write: bool = False):
    import winreg

    access = winreg.KEY_SET_VALUE if write else winreg.KEY_READ
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, access)


def install() -> None:
    import winreg

    with _open(write=True) as key:
        winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command())
    print(f"Installed. Runs at logon:\n  {command()}")


def uninstall() -> None:
    import winreg

    try:
        with _open(write=True) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        print("Removed from startup.")
    except FileNotFoundError:
        print("Not installed.")


def status() -> None:
    import winreg

    try:
        with _open() as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
        print(f"Installed:\n  {value}")
    except FileNotFoundError:
        print("Not installed.")


def main(argv: list[str]) -> int:
    if sys.platform != "win32":
        print("Autostart is Windows only.")
        return 1
    actions = {"install": install, "uninstall": uninstall, "status": status}
    if len(argv) != 1 or argv[0] not in actions:
        print(__doc__)
        return 1
    actions[argv[0]]()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
