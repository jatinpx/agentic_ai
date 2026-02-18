"""
Structured logging utilities for the LinkedIn content agent.
Wraps brain.logger.add_log with LinkedIn-specific prefixes.
"""

import time
from brain.logger import add_log


def log_node(node_name: str, event: str, detail: str = ""):
    """
    Log a structured event for a LinkedIn pipeline node.

    Events:
        AGENT START    — pipeline begins
        NODE EXECUTION — node starts/completes
        STATE UPDATE   — state key modified
        TOKEN USAGE    — LLM token counts (if available)
        ERROR          — node failure
    """
    prefix = f"[LINKEDIN] [{event}] [{node_name}]"
    message = f"{prefix} {detail}" if detail else prefix
    add_log(message)


def log_agent_start(topic: str):
    add_log(f"[LINKEDIN] [AGENT START] linkedin_content_agent — topic: {topic}")


def log_agent_end(post_id: str, viral_score: float):
    add_log(f"[LINKEDIN] [AGENT END] post_id: {post_id} — viral_score: {viral_score}")


def log_state_update(node_name: str, key: str, summary: str = ""):
    add_log(f"[LINKEDIN] [STATE UPDATE] [{node_name}] {key} updated — {summary}")


def log_token_usage(node_name: str, model: str, prompt_tokens: int = 0, completion_tokens: int = 0):
    add_log(
        f"[LINKEDIN] [TOKEN USAGE] [{node_name}] model: {model}, "
        f"prompt_tokens: {prompt_tokens}, completion_tokens: {completion_tokens}"
    )


def log_error(node_name: str, error_message: str):
    add_log(f"[LINKEDIN] [ERROR] [{node_name}] {error_message}")


class NodeTimer:
    """Context manager to time node execution and log it."""

    def __init__(self, node_name: str):
        self.node_name = node_name
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        log_node(self.node_name, "NODE EXECUTION", "started")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = int((time.time() - self.start_time) * 1000)
        if exc_type:
            log_error(self.node_name, f"failed after {elapsed_ms}ms — {exc_val}")
        else:
            log_node(self.node_name, "NODE EXECUTION", f"completed in {elapsed_ms}ms")
        return False  # Don't suppress exceptions
