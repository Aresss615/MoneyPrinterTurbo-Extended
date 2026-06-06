"""Thread-safe cooperative-cancellation registry for video render tasks.

Renders run inside daemon threads (and moviepy/ffmpeg in-process), which Python
cannot force-kill. Instead the pipeline polls :func:`is_canceled` at checkpoints
and aborts gracefully. Kept dependency-free in its own module so the pipeline,
queue, and controller can share it without circular imports.
"""

import threading


_lock = threading.Lock()
_canceled: set[str] = set()


def request_cancel(task_id: str) -> None:
    """Mark ``task_id`` as cancel-requested."""
    if not task_id:
        return
    with _lock:
        _canceled.add(task_id)


def is_canceled(task_id: str) -> bool:
    """Return whether a cancel has been requested for ``task_id``."""
    if not task_id:
        return False
    with _lock:
        return task_id in _canceled


def clear(task_id: str) -> None:
    """Forget any cancel request for ``task_id`` (safe if none exists)."""
    with _lock:
        _canceled.discard(task_id)
