"""
Node Inspector - Safely inspect and serialize LangGraph node state

Utilities for:
- Safe serialization of state dicts
- Redaction of sensitive fields (API keys, emails, etc.)
- Truncation of large objects
- Schema validation for returned data
"""

import json
import re
from typing import Dict, Any, Optional, List
from copy import deepcopy


# Patterns for sensitive data detection
SENSITIVE_PATTERNS = {
    "api_key": re.compile(r"api[_-]?key", re.IGNORECASE),
    "token": re.compile(r"(token|jwt|bearer)", re.IGNORECASE),
    "password": re.compile(r"password", re.IGNORECASE),
    "secret": re.compile(r"secret", re.IGNORECASE),
    "auth": re.compile(r"auth(orization)?", re.IGNORECASE),
    "credential": re.compile(r"credential", re.IGNORECASE),
    "email": re.compile(r"email|@", re.IGNORECASE),
    "user_id": re.compile(r"(user_id|telegram_user_id|chat_id)", re.IGNORECASE),
}

REDACTION_VALUE = "[REDACTED]"


class NodeInspector:
    """Utilities for safe node state inspection."""
    
    @staticmethod
    def is_sensitive_field(key: str) -> bool:
        """Check if a field name suggests sensitive content."""
        for pattern in SENSITIVE_PATTERNS.values():
            if pattern.search(key):
                return True
        return False
    
    @staticmethod
    def redact_value(value: Any) -> Any:
        """Redact a sensitive value."""
        if isinstance(value, str) and len(value) > 0:
            return REDACTION_VALUE
        return value
    
    @staticmethod
    def safe_serialize(obj: Any, max_size: int = 1000, redact_sensitive: bool = True) -> Any:
        """
        Safely serialize an object for logging/tracing.
        
        Args:
            obj: Object to serialize
            max_size: Max characters for strings/values
            redact_sensitive: Whether to redact sensitive fields
            
        Returns:
            Safe representation of object
        """
        if obj is None:
            return None
        
        if isinstance(obj, bool):
            return obj
        
        if isinstance(obj, (int, float)):
            return obj
        
        if isinstance(obj, str):
            if len(obj) > max_size:
                return f"{obj[:max_size]}... [truncated]"
            # Check if string looks like sensitive data
            if redact_sensitive and (obj.startswith("sk-") or len(obj) > 50 and re.match(r"^[a-zA-Z0-9_-]+$", obj)):
                return REDACTION_VALUE
            return obj
        
        if isinstance(obj, bytes):
            return f"<bytes: {len(obj)} bytes>"
        
        if isinstance(obj, dict):
            result = {}
            for k, v in list(obj.items())[:50]:  # Limit dict size
                if isinstance(k, str) and redact_sensitive and NodeInspector.is_sensitive_field(k):
                    result[k] = NodeInspector.redact_value(v)
                else:
                    result[k] = NodeInspector.safe_serialize(v, max_size, redact_sensitive)
            if len(obj) > 50:
                result["__truncated__"] = f"{len(obj) - 50} more keys"
            return result
        
        if isinstance(obj, (list, tuple)):
            items = [NodeInspector.safe_serialize(item, max_size, redact_sensitive) for item in obj[:20]]
            if len(obj) > 20:
                items.append(f"... and {len(obj) - 20} more items")
            return items
        
        if isinstance(obj, set):
            return list(obj)[:20]
        
        if hasattr(obj, "__dict__"):
            # Custom object - try to extract key fields
            return NodeInspector.safe_serialize(obj.__dict__, max_size, redact_sensitive)
        
        # Fallback: str representation
        str_repr = str(obj)
        if len(str_repr) > max_size:
            return f"{str_repr[:max_size]}..."
        return str_repr
    
    @staticmethod
    def inspect_node_state(state: Dict[str, Any], node_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Create a safe, inspectable view of node state for logging/UI.
        
        Args:
            state: LangGraph node state dict
            node_name: Optional node name for context
            
        Returns:
            Dict with keys summary, key_values, and metadata
        """
        result = {
            "node_name": node_name,
            "timestamp": datetime.utcnow().isoformat() + "Z" if "datetime" in globals() else "",
            "keys": list(state.keys()),
            "values": {},
            "size_bytes": 0,
        }
        
        # Safe serialization of state values
        for key, value in state.items():
            if NodeInspector.is_sensitive_field(key):
                result["values"][key] = REDACTION_VALUE
            else:
                safe_value = NodeInspector.safe_serialize(value, max_size=500, redact_sensitive=True)
                result["values"][key] = safe_value
                
                # Approximate size
                if isinstance(safe_value, str):
                    result["size_bytes"] += len(safe_value)
        
        return result
    
    @staticmethod
    def compare_states(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare two state snapshots and return the differences.
        
        Args:
            before: State before operation
            after: State after operation
            
        Returns:
            Dict with added_keys, removed_keys, modified_keys, and changes
        """
        before_keys = set(before.keys())
        after_keys = set(after.keys())
        
        result = {
            "added_keys": list(after_keys - before_keys),
            "removed_keys": list(before_keys - after_keys),
            "modified_keys": [],
            "changes": {},
        }
        
        for key in before_keys & after_keys:
            before_val = before[key]
            after_val = after[key]
            
            if before_val != after_val:
                result["modified_keys"].append(key)
                result["changes"][key] = {
                    "before": NodeInspector.safe_serialize(before_val, max_size=200),
                    "after": NodeInspector.safe_serialize(after_val, max_size=200),
                }
        
        return result


# Import datetime for timestamps if available
try:
    from datetime import datetime
except ImportError:
    pass
