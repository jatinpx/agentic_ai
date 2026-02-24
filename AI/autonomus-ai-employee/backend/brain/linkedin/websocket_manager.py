"""
WebSocket Connection Manager for LinkedIn Pipeline Streaming.

Manages WebSocket connections per thread_id, broadcasts progress events,
and handles graceful disconnections.
"""

import asyncio
import json
from typing import Dict, List, Any, Optional
from fastapi import WebSocket
from datetime import datetime


class ConnectionManager:
    """
    Manages WebSocket connections for LinkedIn pipeline status streaming.
    
    Connections are organized by thread_id, allowing multiple clients
    to watch the same pipeline execution.
    """
    
    def __init__(self):
        # Dict[thread_id, List[WebSocket]]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self._lock = asyncio.Lock()
    
    async def connect(self, thread_id: str, websocket: WebSocket):
        """Register a new WebSocket connection for a thread_id."""
        await websocket.accept()
        
        async with self._lock:
            if thread_id not in self.active_connections:
                self.active_connections[thread_id] = []
            self.active_connections[thread_id].append(websocket)
    
    async def disconnect(self, thread_id: str, websocket: WebSocket):
        """Remove a WebSocket connection from the registry."""
        async with self._lock:
            if thread_id in self.active_connections:
                if websocket in self.active_connections[thread_id]:
                    self.active_connections[thread_id].remove(websocket)
                
                # Clean up empty thread_id entries
                if not self.active_connections[thread_id]:
                    del self.active_connections[thread_id]
    
    async def broadcast(
        self,
        thread_id: str,
        event_type: str,
        data: Dict[str, Any],
        node_name: Optional[str] = None
    ):
        """
        Broadcast a progress event to all connected clients for this thread_id.
        
        Args:
            thread_id: The pipeline thread_id
            event_type: Event type (node_start, node_complete, state_update, error, complete)
            data: Additional data to send with the event
            node_name: Optional node name (for node_start/node_complete events)
        """
        if thread_id not in self.active_connections:
            return
        
        message = {
            "type": event_type,
            "thread_id": thread_id,
            "timestamp": datetime.utcnow().isoformat(),
            "node": node_name,
            **data
        }
        
        # Send to all connected clients for this thread_id
        disconnected = []
        for websocket in self.active_connections[thread_id]:
            try:
                await websocket.send_json(message)
            except Exception as e:
                # Connection broken, mark for removal
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    if ws in self.active_connections[thread_id]:
                        self.active_connections[thread_id].remove(ws)
                
                if not self.active_connections[thread_id]:
                    del self.active_connections[thread_id]
    
    def has_connections(self, thread_id: str) -> bool:
        """Check if there are any active connections for this thread_id."""
        return thread_id in self.active_connections and len(self.active_connections[thread_id]) > 0
    
    def get_connection_count(self, thread_id: str) -> int:
        """Get the number of active connections for this thread_id."""
        return len(self.active_connections.get(thread_id, []))


# Global connection manager instance
ws_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return ws_manager


# Store the main event loop for scheduling from background threads
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """Store a reference to the main event loop for background task broadcasts."""
    global _main_loop
    _main_loop = loop


def broadcast_progress(
    thread_id: str,
    event_type: str,
    node_name: Optional[str] = None,
    **data
):
    """
    Synchronous wrapper to schedule WebSocket broadcast from sync code.
    
    This allows nodes and logging functions to trigger broadcasts
    without needing to be async. Works from both async context and
    background threads.
    
    Usage:
        broadcast_progress(thread_id, "node_start", "fact_verification", detail="Starting...")
    """
    if not thread_id or not ws_manager.has_connections(thread_id):
        return
    
    try:
        # Try to get the running loop (works if we're already in async context)
        try:
            loop = asyncio.get_running_loop()
            # We're in an async context, can use create_task
            asyncio.create_task(
                ws_manager.broadcast(thread_id, event_type, data, node_name)
            )
            return
        except RuntimeError:
            # No running loop - we're in a sync context (background thread)
            pass
        
        # We're in a background thread, use run_coroutine_threadsafe with stored loop
        if _main_loop is not None:
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast(thread_id, event_type, data, node_name),
                _main_loop
            )
        else:
            # Fallback: try to get any event loop
            import logging
            logging.warning(f"[WebSocket] No main loop stored, cannot broadcast from thread")
    except Exception as e:
        # WebSocket is optional, don't break pipeline - but log the error
        import logging
        logging.error(f"[WebSocket] Broadcast failed: {e}", exc_info=True)
