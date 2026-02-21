"""
Structured logging utilities for the LinkedIn content agent.
Wraps brain.logger.add_log with LinkedIn-specific prefixes.
Also broadcasts progress events via WebSocket for live UI updates.
"""

import time
from typing import Optional, Dict, Any
from brain.logger import add_log, _thread_id_var
from brain.linkedin.websocket_manager import broadcast_progress
from brain.linkedin.cancellation import is_abort_requested, PipelineAborted


def log_node(node_name: str, event: str, detail: str = "", metadata: Optional[Dict[str, Any]] = None):
    """
    Log a structured event for a LinkedIn pipeline node.
    Also broadcasts via WebSocket if connections exist.

    Events:
        AGENT START    — pipeline begins
        NODE EXECUTION — node starts/completes
        STATE UPDATE   — state key modified
        TOKEN USAGE    — LLM token counts (if available)
        ERROR          — node failure
    
    Args:
        node_name: Name of the node
        event: Event type
        detail: Human-readable detail message
        metadata: Optional dict with metrics (viral_score, research_confidence, etc.)
    """
    prefix = f"[LINKEDIN] [{event}] [{node_name}]"
    message = f"{prefix} {detail}" if detail else prefix
    add_log(message)
    
    # Broadcast via WebSocket
    thread_id = _thread_id_var.get()
    if thread_id and thread_id != "unknown":
        event_type = "node_complete" if "completed" in detail else "node_start"
        broadcast_progress(
            thread_id,
            event_type,
            node_name=node_name,
            detail=detail,
            event_name=event,
            metadata=metadata or {}
        )


def log_agent_start(topic: str):
    add_log(f"[LINKEDIN] [AGENT START] linkedin_content_agent — topic: {topic}")
    
    # Broadcast pipeline start
    thread_id = _thread_id_var.get()
    if thread_id and thread_id != "unknown":
        broadcast_progress(
            thread_id,
            "pipeline_start",
            topic=topic,
            detail="LinkedIn content pipeline initializing"
        )


def log_agent_end(post_id: str, viral_score: float, final_post: dict = None, iteration_count: int = 0, hooks: list = None, realism_score: float = 0.0):
    add_log(f"[LINKEDIN] [AGENT END] post_id: {post_id} — viral_score: {viral_score}")
    
    # Broadcast pipeline completion with full post data, hooks, and scores
    thread_id = _thread_id_var.get()
    if thread_id and thread_id != "unknown":
        broadcast_progress(
            thread_id,
            "pipeline_complete",
            post_id=post_id,
            viral_score=viral_score,
            realism_score=realism_score,
            final_post=final_post or {},
            hooks=hooks or [],
            iteration_count=iteration_count,
            detail="Pipeline completed successfully"
        )


def log_state_update(node_name: str, key: str, summary: str = "", value: Any = None):
    add_log(f"[LINKEDIN] [STATE UPDATE] [{node_name}] {key} updated — {summary}")
    
    # Broadcast state change
    thread_id = _thread_id_var.get()
    if thread_id and thread_id != "unknown":
        broadcast_progress(
            thread_id,
            "state_update",
            node_name=node_name,
            key=key,
            summary=summary,
            value=value
        )


def log_token_usage(node_name: str, model: str, prompt_tokens: int = 0, completion_tokens: int = 0):
    add_log(
        f"[LINKEDIN] [TOKEN USAGE] [{node_name}] model: {model}, "
        f"prompt_tokens: {prompt_tokens}, completion_tokens: {completion_tokens}"
    )


def log_error(node_name: str, error_message: str):
    add_log(f"[LINKEDIN] [ERROR] [{node_name}] {error_message}")
    
    # Broadcast error
    thread_id = _thread_id_var.get()
    if thread_id and thread_id != "unknown":
        broadcast_progress(
            thread_id,
            "error",
            node_name=node_name,
            error=error_message,
            detail=f"Error in {node_name}: {error_message}"
        )


def log_usage_update(usage_summary: Dict[str, Any]):
    """
    Broadcast API usage stats (LLM calls, tokens, search calls) via WebSocket.
    
    Args:
        usage_summary: Dict with keys: llm_calls, search_calls, total_tokens, etc.
    """
    thread_id = _thread_id_var.get()
    if thread_id and thread_id != "unknown":
        broadcast_progress(
            thread_id,
            "usage_update",
            detail="API usage updated",
            metadata=usage_summary
        )


class NodeTimer:
    """Context manager to time node execution and log it."""

    def __init__(self, node_name: str, metadata: Optional[Dict[str, Any]] = None):
        self.node_name = node_name
        self.start_time = None
        self.metadata = metadata or {}

    def __enter__(self):
        thread_id = _thread_id_var.get()
        if thread_id and thread_id != "unknown" and is_abort_requested(thread_id):
            log_node(self.node_name, "NODE EXECUTION", "skipped — pipeline aborted")
            raise PipelineAborted(f"Pipeline aborted by user (thread={thread_id})")

        self.start_time = time.time()
        log_node(self.node_name, "NODE EXECUTION", "started", metadata=self.metadata)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        from brain.linkedin.usage_tracker import get_usage_tracker
        
        elapsed_ms = int((time.time() - self.start_time) * 1000)
        if exc_type:
            log_error(self.node_name, f"failed after {elapsed_ms}ms — {exc_val}")
        else:
            completion_metadata = {**self.metadata, "elapsed_ms": elapsed_ms}
            log_node(
                self.node_name,
                "NODE EXECUTION",
                f"completed in {elapsed_ms}ms",
                metadata=completion_metadata
            )
            
            # Broadcast usage update after each node completes
            tracker = get_usage_tracker()
            log_usage_update(tracker.get_summary())
            
        return False  # Don't suppress exceptions
