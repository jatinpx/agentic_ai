"""
Exception Tracker - Capture and track exceptions with context

Handles:
- Capturing full stack traces with local context
- Emitting exceptions to observability system
- Storing exceptions in persistent log
"""

import traceback
import sys
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from services.observability_service import get_observability_manager

logger = logging.getLogger(__name__)


class ExceptionTracker:
    """Service for tracking exceptions with full context."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
    
    @staticmethod
    def capture_exception(
        exc: Exception,
        context: Optional[str] = None,
        additional_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Capture exception with full context and emit to observability system.
        
        Args:
            exc: Exception to capture
            context: Optional context string (e.g., "fact_verification", "webhook_processing")
            additional_data: Optional dict with additional context
            
        Returns:
            Exception event dict
        """
        exc_type, exc_value, exc_tb = sys.exc_info()
        
        # Get stack trace
        stack_lines = traceback.format_tb(exc_tb)
        stack_trace = "".join(stack_lines)
        
        # Extract local variables from traceback frames
        local_vars = {}
        try:
            tb = exc_tb
            while tb is not None:
                frame = tb.tb_frame
                local_vars[f"frame_{tb.tb_lineno}"] = {
                    "filename": frame.f_code.co_filename,
                    "function": frame.f_code.co_name,
                    "lineno": tb.tb_lineno,
                    "locals_sample": str(frame.f_locals)[:200],  # Truncated
                }
                tb = tb.tb_next
        except Exception as e:
            logger.warning(f"Could not extract local vars: {e}")
        
        # Build exception event
        event = {
            "type": "exception",
            "correlation_id": get_observability_manager().get_correlation_id(),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "exception_type": exc_type.__name__ if exc_type else "UnknownException",
            "exception_message": str(exc),
            "context": context,
            "stack_trace": stack_trace,
            "local_vars": local_vars,
            "additional_data": additional_data or {},
        }
        
        # Emit to observability system
        obs = get_observability_manager()
        obs._emit_event(event)
        
        logger.error(
            f"[EXCEPTION] {event['exception_type']}: {event['exception_message']} | context={context}",
            exc_info=exc
        )
        
        return event
    
    @staticmethod
    def log_with_context(
        exc: Exception,
        context: str,
        node_name: Optional[str] = None,
        state: Optional[Dict[str, Any]] = None,
    ):
        """
        Log exception with full observability context.
        
        Args:
            exc: Exception to log
            context: Context description (e.g., "node_execution", "webhook_processing")
            node_name: If exception occurred in a node, its name
            state: If exception occurred during node execution, the state before error
        """
        from brain.linkedin.node_inspector import NodeInspector
        
        additional_data = {}
        if node_name:
            additional_data["node_name"] = node_name
        if state:
            additional_data["state_snapshot"] = NodeInspector.safe_serialize(state, max_size=500)
        
        ExceptionTracker.capture_exception(
            exc=exc,
            context=context,
            additional_data=additional_data,
        )


def get_exception_tracker() -> ExceptionTracker:
    """Get the singleton exception tracker."""
    return ExceptionTracker()


def safe_execute(
    func,
    context: str,
    node_name: Optional[str] = None,
    default_value: Any = None,
):
    """
    Execute a function with exception tracking.
    
    Args:
        func: Function to execute
        context: Context description
        node_name: Optional node name
        default_value: Value to return on exception
        
    Returns:
        Result of func or default_value if exception occurs
    """
    try:
        return func()
    except Exception as e:
        get_exception_tracker().log_with_context(
            exc=e,
            context=context,
            node_name=node_name,
        )
        return default_value
