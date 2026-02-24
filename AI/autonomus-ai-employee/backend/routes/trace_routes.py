"""
Trace Routes - API endpoints for retrieving and viewing observability traces

Endpoints:
- GET /trace/{correlation_id} - Retrieve full trace by correlation ID
- GET /trace/nodes/{node_name} - Retrieve recent traces by node
- GET /trace/live/{thread_id} - WebSocket for live trace streaming
- GET /trace/health - Observability system health
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query
from datetime import datetime, timedelta

from services.observability_service import get_observability_manager
from db.event_log_store import get_event_log_store
from brain.linkedin.websocket_manager import get_connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trace", tags=["observability"])

# Track active trace subscriptions
_trace_subscriptions: Dict[str, WebSocket] = {}


# ==================== HTTP Endpoints ====================

@router.get("/{correlation_id}")
async def get_trace(correlation_id: str) -> Dict[str, Any]:
    """
    Retrieve full trace for a correlation ID.
    
    Returns ordered list of spans with input/output data.
    """
    obs = get_observability_manager()
    spans = await obs.get_trace(correlation_id)
    
    if not spans:
        raise HTTPException(status_code=404, detail=f"No trace found for {correlation_id}")
    
    return {
        "correlation_id": correlation_id,
        "span_count": len(spans),
        "spans": spans,
        "duration_ms": _calculate_trace_duration(spans),
        "first_timestamp": spans[0].get("timestamp") if spans else None,
        "last_timestamp": spans[-1].get("timestamp") if spans else None,
    }


@router.get("/nodes/{node_name}")
async def get_node_traces(
    node_name: str,
    limit: int = Query(50, ge=1, le=500),
    lookback_minutes: int = Query(60, ge=1, le=1440),
) -> Dict[str, Any]:
    """
    Retrieve recent traces for a specific node.
    
    Args:
        node_name: Name of the node (e.g., "fact_verification_node", "post_writer_node")
        limit: Max number of traces to return
        lookback_minutes: How far back to search
    """
    obs = get_observability_manager()
    
    # Get spans from memory (for now; would query DB in full implementation)
    spans = obs.get_spans_by_node(node_name)
    
    # Filter by time
    cutoff = datetime.utcnow() - timedelta(minutes=lookback_minutes)
    recent_spans = [
        s for s in spans
        if s.timestamp >= cutoff.isoformat() + "Z"
    ][-limit:]
    
    # Group by correlation_id
    traces_by_correlation = {}
    for span in recent_spans:
        corr_id = span.correlation_id
        if corr_id not in traces_by_correlation:
            traces_by_correlation[corr_id] = []
        traces_by_correlation[corr_id].append(span)
    
    return {
        "node_name": node_name,
        "trace_count": len(traces_by_correlation),
        "span_count": len(recent_spans),
        "lookback_minutes": lookback_minutes,
        "traces": {
            corr_id: {
                "correlation_id": corr_id,
                "span_count": len(spans),
                "spans": spans,
            }
            for corr_id, spans in traces_by_correlation.items()
        }
    }


@router.get("/health")
async def trace_system_health() -> Dict[str, Any]:
    """Get health status of observability system."""
    obs = get_observability_manager()
    
    return {
        "status": "healthy",
        "spans_in_memory": len(obs._spans),
        "event_callbacks_registered": len(obs._event_callbacks),
        "event_store_configured": obs._event_store_callback is not None,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ==================== WebSocket Endpoints ====================

@router.websocket("/live/{thread_id}")
async def websocket_live_trace(websocket: WebSocket, thread_id: str):
    """
    WebSocket endpoint for live trace streaming.
    
    Client receives real-time span_start, span_end, and error events.
    """
    await websocket.accept()
    logger.info(f"[TRACE WS] Client connected for thread {thread_id}")
    
    _trace_subscriptions[thread_id] = websocket
    obs = get_observability_manager()
    
    try:
        # Register callback to stream events to this client
        async def stream_event(event: Dict[str, Any]):
            # Only stream events for this thread
            if event.get("thread_id") == thread_id or not event.get("thread_id"):
                try:
                    await websocket.send_json(event)
                except Exception as e:
                    logger.error(f"Error sending trace event: {e}")
        
        obs.register_event_callback(stream_event)
        
        # Keep connection open
        while True:
            data = await websocket.receive_text()
            # Handle client commands (optional)
            if data == "ping":
                await websocket.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat()})
            elif data == "get_stats":
                stats = {
                    "type": "stats",
                    "spans_in_memory": len(obs._spans),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
                await websocket.send_json(stats)
    
    except WebSocketDisconnect:
        logger.info(f"[TRACE WS] Client disconnected from thread {thread_id}")
        if thread_id in _trace_subscriptions:
            del _trace_subscriptions[thread_id]
    except Exception as e:
        logger.error(f"[TRACE WS] Error: {e}")
        if thread_id in _trace_subscriptions:
            del _trace_subscriptions[thread_id]


# ==================== Helper Functions ====================

def _calculate_trace_duration(spans: list) -> Optional[float]:
    """Calculate total duration of trace in ms."""
    if not spans or len(spans) < 2:
        return None
    
    first_time = min((s.get("start_time") for s in spans if s.get("start_time")), default=None)
    last_time = max((s.get("timestamp") for s in spans if s.get("timestamp")), default=None)
    
    if first_time and last_time:
        try:
            first_dt = datetime.fromisoformat(first_time.replace("Z", "+00:00"))
            last_dt = datetime.fromisoformat(last_time.replace("Z", "+00:00"))
            return (last_dt - first_dt).total_seconds() * 1000
        except:
            pass
    
    return None
