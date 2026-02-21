import os
import time
import uuid
import contextvars

INSTANCE_ID = str(uuid.uuid4())
_thread_id_var = contextvars.ContextVar("thread_id", default="unknown")
_iteration_count_var = contextvars.ContextVar("iteration_count", default=0)

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "logs")
LOG_FILE = os.path.join(LOG_DIR, "log.txt")


def set_thread_id(thread_id: str) -> None:
    _thread_id_var.set(thread_id)


def clear_thread_id() -> None:
    _thread_id_var.set("unknown")


def set_iteration_count(iteration: int) -> None:
    """Set the current iteration count for this context."""
    _iteration_count_var.set(iteration)


def get_iteration_count() -> int:
    """Get the current iteration count for this context."""
    return _iteration_count_var.get()


def add_log(message: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    thread_id = _thread_id_var.get()
    entry = f"[{timestamp}] [instance:{INSTANCE_ID}] [thread:{thread_id}] {message}"
    print(entry)

    os.makedirs(LOG_DIR, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(entry + "\n")
