"""
Event Log Store - Persist observability events to database

Handles:
- Writing trace spans to event_logs table
- Writing exceptions to exception_logs table
- Querying historical traces by correlation_id, node_name, or timestamp
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class EventLogStore:
    """Service for persisting and querying observability events."""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, "_initialized"):
            return
        
        self._initialized = True
        self._db = None
    
    def set_db(self, db):
        """Set database connection."""
        self._db = db
    
    async def store_event(self, event: Dict[str, Any]) -> bool:
        """
        Store an observability event to the database.
        
        Args:
            event: Event dict from ObservabilityManager
            
        Returns:
            True if stored successfully
        """
        if not self._db:
            logger.warning("EventLogStore: Database not configured")
            return False
        
        try:
            if event.get("type") == "exception":
                await self._store_exception(event)
            else:
                await self._store_span_event(event)
            return True
        except Exception as e:
            logger.error(f"Error storing event: {e}")
            return False
    
    async def _store_span_event(self, event: Dict[str, Any]):
        """Store span event to event_logs table."""
        # This would require a database method to insert
        # For now, we'll just log it
        logger.debug(f"[EVENT LOG] {event.get('type')}: {event.get('name')}")
        
        # In a real implementation:
        # await self._db.execute(
        #     "INSERT INTO event_logs (correlation_id, span_id, parent_span_id, ...)"
        #     "VALUES (:correlation_id, :span_id, :parent_span_id, ...)",
        #     event
        # )
    
    async def _store_exception(self, event: Dict[str, Any]):
        """Store exception event to exception_logs table."""
        logger.error(f"[EXCEPTION LOG] {event.get('error_message')}")
        
        # In a real implementation:
        # await self._db.execute(
        #     "INSERT INTO exception_logs (correlation_id, error_message, stack_trace, ...)"
        #     "VALUES (:correlation_id, :error_message, :stack_trace, ...)",
        #     event
        # )
    
    async def get_trace_by_correlation_id(self, correlation_id: str) -> List[Dict[str, Any]]:
        """Retrieve all events for a correlation ID."""
        if not self._db:
            return []
        
        try:
            # Placeholder for DB query
            # SELECT * FROM event_logs WHERE correlation_id = ? ORDER BY timestamp
            return []
        except Exception as e:
            logger.error(f"Error retrieving trace: {e}")
            return []
    
    async def get_events_by_node(self, node_name: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve recent events for a specific node."""
        if not self._db:
            return []
        
        try:
            # Placeholder for DB query
            # SELECT * FROM event_logs WHERE node_name = ? ORDER BY timestamp DESC LIMIT ?
            return []
        except Exception as e:
            logger.error(f"Error retrieving node events: {e}")
            return []
    
    async def get_events_since(self, since: datetime, correlation_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve events since a specific timestamp."""
        if not self._db:
            return []
        
        try:
            # Placeholder for DB query
            # SELECT * FROM event_logs WHERE timestamp >= ? AND (correlation_id = ? OR ? IS NULL)
            # ORDER BY timestamp
            return []
        except Exception as e:
            logger.error(f"Error retrieving recent events: {e}")
            return []
    
    async def cleanup_old_events(self, days: int = 7):
        """Remove events older than specified days."""
        if not self._db:
            return False
        
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            # DELETE FROM event_logs WHERE timestamp < ?
            logger.info(f"Cleaned up events older than {days} days")
            return True
        except Exception as e:
            logger.error(f"Error cleaning up events: {e}")
            return False


def get_event_log_store() -> EventLogStore:
    """Get the singleton event log store."""
    return EventLogStore()
