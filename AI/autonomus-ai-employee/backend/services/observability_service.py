"""
Observability Service - Centralized Tracing & Correlation

Manages:
- Correlation IDs across requests and async tasks
- Span creation/tracking (local, OTEL-compatible)
- Event emission (WebSocket + persistent store)
- Context propagation through asyncio
"""

import uuid
import time
import asyncio
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from contextvars import ContextVar
from dataclasses import dataclass, asdict
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Context variables for async propagation
_correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")
_span_id_var: ContextVar[str] = ContextVar("span_id", default="")
_parent_span_id_var: ContextVar[Optional[str]] = ContextVar("parent_span_id", default=None)


@dataclass
class Span:
    """Represents a traced operation."""
    span_id: str
    parent_span_id: Optional[str]
    correlation_id: str
    name: str
    node_name: Optional[str]
    event_type: str  # "node_start", "node_end", "api_call", "db_query", etc.
    timestamp: str
    start_time: float
    latency_ms: Optional[float] = None
    status: str = "ok"  # "ok", "error", "pending"
    input_data: Optional[Dict[str, Any]] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    thread_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, excluding None values and large objects."""
        data = asdict(self)
        # Remove None values for cleaner JSON
        return {k: v for k, v in data.items() if v is not None}


class ObservabilityManager:
    """Singleton observability manager."""
    
    _instance = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        
        self._initialized = True
        self._spans: Dict[str, Span] = {}  # span_id -> Span
        self._event_callbacks: List[Callable] = []  # For WebSocket emission
        self._event_store_callback: Optional[Callable] = None  # For DB persistence
        
    def set_event_store_callback(self, callback: Callable):
        """Register callback for persisting events to database."""
        self._event_store_callback = callback
    
    def register_event_callback(self, callback: Callable):
        """Register callback for event emission (e.g., WebSocket broadcast)."""
        self._event_callbacks.append(callback)
    
    def generate_correlation_id(self) -> str:
        """Generate a new correlation ID."""
        return str(uuid.uuid4())
    
    def get_correlation_id(self) -> str:
        """Get current correlation ID or generate new one."""
        correlation_id = _correlation_id_var.get()
        if not correlation_id:
            correlation_id = self.generate_correlation_id()
            _correlation_id_var.set(correlation_id)
        return correlation_id
    
    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for current context."""
        _correlation_id_var.set(correlation_id)
    
    def generate_span_id(self) -> str:
        """Generate a new span ID."""
        return str(uuid.uuid4())[:12]  # Short ID for readability
    
    def start_span(
        self,
        name: str,
        event_type: str,
        node_name: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
    ) -> Span:
        """Create and start a new span."""
        correlation_id = self.get_correlation_id()
        parent_span_id = _parent_span_id_var.get()
        span_id = self.generate_span_id()
        
        span = Span(
            span_id=span_id,
            parent_span_id=parent_span_id,
            correlation_id=correlation_id,
            name=name,
            node_name=node_name,
            event_type=event_type,
            timestamp=datetime.utcnow().isoformat() + "Z",
            start_time=time.time(),
            input_data=input_data,
            metadata=metadata,
            thread_id=thread_id,
        )
        
        self._spans[span_id] = span
        
        # Emit span start event
        self._emit_event({
            "type": "span_start",
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "correlation_id": correlation_id,
            "name": name,
            "event_type": event_type,
            "node_name": node_name,
            "timestamp": span.timestamp,
            "thread_id": thread_id,
        })
        
        logger.debug(f"[SPAN START] {name} | correlation_id={correlation_id} | span_id={span_id}")
        
        return span
    
    def end_span(
        self,
        span: Span,
        output_data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        status: str = "ok",
    ):
        """Complete a span."""
        span.latency_ms = (time.time() - span.start_time) * 1000
        span.output_data = output_data
        span.error_message = error
        span.status = status
        
        # Emit span end event
        self._emit_event({
            "type": "span_end",
            "span_id": span.span_id,
            "parent_span_id": span.parent_span_id,
            "correlation_id": span.correlation_id,
            "name": span.name,
            "event_type": span.event_type,
            "node_name": span.node_name,
            "status": status,
            "latency_ms": span.latency_ms,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "thread_id": span.thread_id,
        })
        
        logger.debug(f"[SPAN END] {span.name} | latency={span.latency_ms:.1f}ms | status={status}")
    
    def _emit_event(self, event: Dict[str, Any]):
        """Emit event to registered callbacks."""
        # WebSocket callbacks
        for callback in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(event))
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")
        
        # Event store callback (persistent logging)
        if self._event_store_callback:
            try:
                if asyncio.iscoroutinefunction(self._event_store_callback):
                    asyncio.create_task(self._event_store_callback(event))
                else:
                    self._event_store_callback(event)
            except Exception as e:
                logger.error(f"Error in event store callback: {e}")
    
    async def get_trace(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Retrieve all spans for a correlation ID."""
        matching_spans = [
            span.to_dict()
            for span in self._spans.values()
            if span.correlation_id == correlation_id
        ]
        return sorted(matching_spans, key=lambda x: x.get("timestamp", ""))
    
    def get_spans_by_node(self, node_name: str) -> List[Span]:
        """Retrieve all spans for a specific node."""
        return [span for span in self._spans.values() if span.node_name == node_name]


def get_observability_manager() -> ObservabilityManager:
    """Get the singleton observability manager."""
    return ObservabilityManager()


def instrument_function(
    event_type: str = "function_call",
    node_name: Optional[str] = None,
    capture_args: bool = False,
    capture_result: bool = False,
):
    """
    Decorator to automatically trace function execution.
    
    Args:
        event_type: Type of event (e.g., "node_call", "api_call", "db_query")
        node_name: Optional node identifier
        capture_args: Whether to capture function arguments
        capture_result: Whether to capture return value
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            obs = get_observability_manager()
            
            input_data = None
            if capture_args:
                # Safely capture args/kwargs without including 'self'
                safe_args = [str(a)[:200] for a in args[1:] if not hasattr(a, '__dict__')]
                safe_kwargs = {k: str(v)[:200] for k, v in kwargs.items() if not k.startswith('_')}
                input_data = {"args": safe_args[:3], "kwargs": safe_kwargs}
            
            span = obs.start_span(
                name=func.__name__,
                event_type=event_type,
                node_name=node_name,
                input_data=input_data,
            )
            
            try:
                result = await func(*args, **kwargs)
                output_data = None
                if capture_result:
                    output_data = str(result)[:200] if result else None
                obs.end_span(span, output_data=output_data, status="ok")
                return result
            except Exception as e:
                obs.end_span(span, error=str(e), status="error")
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            obs = get_observability_manager()
            
            input_data = None
            if capture_args:
                safe_args = [str(a)[:200] for a in args[1:] if not hasattr(a, '__dict__')]
                safe_kwargs = {k: str(v)[:200] for k, v in kwargs.items() if not k.startswith('_')}
                input_data = {"args": safe_args[:3], "kwargs": safe_kwargs}
            
            span = obs.start_span(
                name=func.__name__,
                event_type=event_type,
                node_name=node_name,
                input_data=input_data,
            )
            
            try:
                result = func(*args, **kwargs)
                output_data = None
                if capture_result:
                    output_data = str(result)[:200] if result else None
                obs.end_span(span, output_data=output_data, status="ok")
                return result
            except Exception as e:
                obs.end_span(span, error=str(e), status="error")
                raise
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
