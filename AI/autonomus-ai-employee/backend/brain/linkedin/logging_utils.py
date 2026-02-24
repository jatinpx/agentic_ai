"""
Structured logging utilities for the LinkedIn content agent.
Wraps brain.logger.add_log with LinkedIn-specific prefixes.
Also broadcasts progress events via WebSocket for live UI updates.
Integrates with ObservabilityService for distributed tracing and correlation.
"""

import time
from typing import Optional, Dict, Any
from brain.logger import add_log, _thread_id_var
from brain.linkedin.websocket_manager import broadcast_progress
from brain.linkedin.cancellation import is_abort_requested, PipelineAborted

# Optional observability integration (graceful fallback if service not available)
try:
    from services.observability_service import get_observability_manager
    OBSERVABILITY_ENABLED = True
except ImportError:
    OBSERVABILITY_ENABLED = False
    get_observability_manager = lambda: None


def _emit_to_observability(
    event_type: str,
    node_name: Optional[str] = None,
    input_data: Optional[Dict[str, Any]] = None,
    output_data: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
):
    """
    Emit a structured event to the observability service.
    Gracefully handles case where observability is not available.
    """
    if not OBSERVABILITY_ENABLED:
        return
    
    try:
        obs = get_observability_manager()
        if not obs:
            return
        
        thread_id = _thread_id_var.get()
        
        # Emit event for tracing
        obs._emit_event({
            "type": event_type,
            "node_name": node_name,
            "timestamp": time.time(),
            "thread_id": thread_id,
            "input_data": input_data,
            "output_data": output_data,
            "metadata": metadata,
            "error_message": error_message,
            "correlation_id": obs.get_correlation_id(),
        })
    except Exception:
        pass  # Observability failures should not crash the pipeline


def log_node(node_name: str, event: str, detail: str = "", metadata: Optional[Dict[str, Any]] = None):
    """
    Log a structured event for a LinkedIn pipeline node.
    Also broadcasts via WebSocket if connections exist.
    Emits to observability service for distributed tracing.

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
    
    # Emit to observability service
    event_type = "node_start" if "started" in detail else ("node_end" if "completed" in detail else "node_event")
    _emit_to_observability(
        event_type=f"node_{event.lower().replace(' ', '_')}",
        node_name=node_name,
        metadata=metadata or {},
    )
    
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
    
    # Emit to observability
    _emit_to_observability(
        event_type="pipeline_start",
        node_name="linkedin_content_agent",
        metadata={"topic": topic},
    )
    
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
    
    # Emit to observability
    _emit_to_observability(
        event_type="pipeline_end",
        node_name="linkedin_content_agent",
        output_data={
            "post_id": post_id,
            "viral_score": viral_score,
            "realism_score": realism_score,
            "iteration_count": iteration_count,
        },
        metadata={
            "post_id": post_id,
            "viral_score": viral_score,
            "realism_score": realism_score,
            "iteration_count": iteration_count,
        },
    )
    
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
    
    # Emit to observability
    _emit_to_observability(
        event_type="state_update",
        node_name=node_name,
        metadata={"key": key, "summary": summary, "value_type": type(value).__name__},
    )
    
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
    
    # Emit to observability
    _emit_to_observability(
        event_type="token_usage",
        node_name=node_name,
        metadata={
            "model": model,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    )


def log_error(node_name: str, error_message: str):
    add_log(f"[LINKEDIN] [ERROR] [{node_name}] {error_message}")
    
    # Emit to observability with error flag
    _emit_to_observability(
        event_type="error",
        node_name=node_name,
        error_message=error_message,
    )
    
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
    Emit to observability service for aggregated metrics.
    
    Args:
        usage_summary: Dict with keys: llm_calls, search_calls, total_tokens, etc.
    """
    # Emit to observability
    _emit_to_observability(
        event_type="usage_update",
        metadata=usage_summary,
    )
    
    # Broadcast via WebSocket
    thread_id = _thread_id_var.get()
    if thread_id and thread_id != "unknown":
        broadcast_progress(
            thread_id,
            "usage_update",
            detail="API usage updated",
            metadata=usage_summary
        )


class NodeTimer:
    """Context manager to time node execution and log it with observability spans."""

    def __init__(self, node_name: str, metadata: Optional[Dict[str, Any]] = None):
        self.node_name = node_name
        self.start_time = None
        self.metadata = metadata or {}
        self.span = None

    def __enter__(self):
        thread_id = _thread_id_var.get()
        if thread_id and thread_id != "unknown" and is_abort_requested(thread_id):
            log_node(self.node_name, "NODE EXECUTION", "skipped — pipeline aborted")
            raise PipelineAborted(f"Pipeline aborted by user (thread={thread_id})")

        self.start_time = time.time()
        
        # Create observability span if available
        if OBSERVABILITY_ENABLED:
            try:
                obs = get_observability_manager()
                if obs:
                    self.span = obs.start_span(
                        name=self.node_name,
                        event_type="node_execution",
                        node_name=self.node_name,
                        metadata=self.metadata,
                        thread_id=thread_id if thread_id != "unknown" else None,
                    )
            except Exception:
                pass  # Observability failures should not crash
        
        log_node(self.node_name, "NODE EXECUTION", "started", metadata=self.metadata)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        from brain.linkedin.usage_tracker import get_usage_tracker
        
        elapsed_ms = int((time.time() - self.start_time) * 1000)
        
        # End observability span if it was created
        if self.span and OBSERVABILITY_ENABLED:
            try:
                obs = get_observability_manager()
                if obs:
                    if exc_type:
                        obs.end_span(self.span, error=str(exc_val), status="error")
                    else:
                        obs.end_span(
                            self.span,
                            output_data={"elapsed_ms": elapsed_ms},
                            status="ok"
                        )
            except Exception:
                pass  # Observability failures should not crash
        
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

