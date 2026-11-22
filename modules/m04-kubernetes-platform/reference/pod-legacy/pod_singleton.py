"""Ensure only one pod-server process runs at a time (fcntl file lock)."""
from __future__ import annotations

import atexit
import fcntl
import os
import sys
from typing import Optional

_LOCK_FD: Optional[int] = None


def lock_path() -> str:
    root = os.path.dirname(os.path.abspath(__file__))
    return os.environ.get("POD_LOCKFILE", os.path.join(root, "pod-server.lock"))


def acquire() -> None:
    """Acquire exclusive lock or exit with a clear message."""
    global _LOCK_FD
    path = lock_path()
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    _LOCK_FD = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(_LOCK_FD, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        other_pid = ""
        try:
            os.lseek(_LOCK_FD, 0, os.SEEK_SET)
            other_pid = os.read(_LOCK_FD, 64).decode("utf-8", errors="ignore").strip()
        except OSError:
            pass
        print(
            "ERROR: Another pod-server instance is already running or starting.",
            flush=True,
        )
        if other_pid:
            print(f"  lock holder pid: {other_pid}", flush=True)
        print(
            "  bash start-pod-server.sh status\n"
            "  bash start-pod-server.sh stop    # to stop the running instance",
            flush=True,
        )
        sys.exit(1)
    os.ftruncate(_LOCK_FD, 0)
    os.write(_LOCK_FD, str(os.getpid()).encode("utf-8"))
    atexit.register(release)


def release() -> None:
    global _LOCK_FD
    if _LOCK_FD is None:
        return
    try:
        fcntl.flock(_LOCK_FD, fcntl.LOCK_UN)
        os.close(_LOCK_FD)
    except OSError:
        pass
    _LOCK_FD = None
