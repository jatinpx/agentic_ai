"""
Thread-level cancellation registry for LinkedIn pipeline runs.

Used to propagate user abort requests into currently running background tasks.
"""

from threading import Lock


class PipelineAborted(Exception):
    """Raised when a LinkedIn pipeline run is cancelled by user action."""


_abort_lock = Lock()
_aborted_threads: set[str] = set()


def request_abort(thread_id: str) -> None:
    """Mark a thread as aborted."""
    if not thread_id:
        return
    with _abort_lock:
        _aborted_threads.add(thread_id)


def clear_abort(thread_id: str) -> None:
    """Clear abort marker for a thread (typically before a new run)."""
    if not thread_id:
        return
    with _abort_lock:
        _aborted_threads.discard(thread_id)


def is_abort_requested(thread_id: str) -> bool:
    """Return True if abort was requested for this thread."""
    if not thread_id:
        return False
    with _abort_lock:
        return thread_id in _aborted_threads
