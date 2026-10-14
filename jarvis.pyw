"""Windowless launcher used by autostart. Double-click also works."""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

from core.main import main  # noqa: E402

main(startup=True)
