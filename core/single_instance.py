"""Make sure only one Jarvis runs at a time (Windows named mutex)."""
from __future__ import annotations

import sys

_handle = None  # kept alive for the life of the process

ERROR_ALREADY_EXISTS = 183


def acquire(name: str = "Local\\JarvisAssistant") -> bool:
    """Return True if this is the only running instance."""
    global _handle
    if sys.platform != "win32":
        return True
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _handle = kernel32.CreateMutexW(None, False, name)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS
