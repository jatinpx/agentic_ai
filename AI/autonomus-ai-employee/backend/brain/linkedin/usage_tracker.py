"""
Token and API usage tracking for LinkedIn agent pipeline.
Tracks all LLM calls (prompt/completion tokens) and Tavily search API calls.
"""
from typing import Dict, Any, Optional
from datetime import datetime
import json

class UsageTracker:
    """Thread-safe usage tracker for LLM and search API calls."""
    
    def __init__(self):
        self.llm_calls = 0
        self.search_calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.call_log = []
        self.start_time = datetime.now()
    
    def log_llm_call(self, 
                     node_name: str, 
                     prompt_tokens: int = 0, 
                     completion_tokens: int = 0,
                     model: str = "unknown",
                     purpose: str = "") -> None:
        """Log an LLM API call with token counts."""
        self.llm_calls += 1
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += (prompt_tokens + completion_tokens)
        
        self.call_log.append({
            "type": "llm",
            "node": node_name,
            "model": model,
            "purpose": purpose,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "timestamp": datetime.now().isoformat()
        })
    
    def log_search_call(self, 
                       node_name: str, 
                       query: str = "",
                       num_results: int = 0) -> None:
        """Log a Tavily search API call."""
        self.search_calls += 1
        
        self.call_log.append({
            "type": "search",
            "node": node_name,
            "query": query[:100],  # Truncate long queries
            "num_results": num_results,
            "timestamp": datetime.now().isoformat()
        })
    
    def get_summary(self) -> Dict[str, Any]:
        """Get aggregated usage summary."""
        from brain.logger import get_iteration_count
        
        elapsed = (datetime.now() - self.start_time).total_seconds()
        iteration_count = get_iteration_count()
        
        return {
            "llm_calls": self.llm_calls,
            "search_calls": self.search_calls,
            "total_api_calls": self.llm_calls + self.search_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "elapsed_seconds": round(elapsed, 2),
            "calls_per_minute": round((self.llm_calls + self.search_calls) / max(elapsed / 60, 0.01), 1),
            "iteration_count": iteration_count
        }
    
    def get_detailed_log(self) -> list:
        """Get full call log with all details."""
        return self.call_log
    
    def merge(self, other: 'UsageTracker') -> None:
        """Merge another tracker's stats into this one."""
        self.llm_calls += other.llm_calls
        self.search_calls += other.search_calls
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.total_tokens += other.total_tokens
        self.call_log.extend(other.call_log)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for state storage."""
        return {
            "summary": self.get_summary(),
            "log": self.call_log
        }


# Global tracker instance (per pipeline run)
_current_tracker: Optional[UsageTracker] = None

def init_usage_tracker() -> UsageTracker:
    """Initialize a new usage tracker for a pipeline run."""
    global _current_tracker
    _current_tracker = UsageTracker()
    return _current_tracker

def get_usage_tracker() -> UsageTracker:
    """Get the current usage tracker, creating one if needed."""
    global _current_tracker
    if _current_tracker is None:
        _current_tracker = UsageTracker()
    return _current_tracker

def reset_usage_tracker() -> None:
    """Reset the global tracker."""
    global _current_tracker
    _current_tracker = None


def track_llm_call(node_name: str, 
                   response: Any = None,
                   prompt_tokens: int = 0,
                   completion_tokens: int = 0,
                   model: str = "ollama",
                   purpose: str = "") -> None:
    """
    Helper to track LLM call. Can extract tokens from response object if available.
    
    Usage:
        response = chat([...])
        track_llm_call("research_quality", response, model="gpt-4", purpose="Quality assessment")
    """
    tracker = get_usage_tracker()
    
    # Try to extract token counts from response if not provided
    if response and hasattr(response, 'usage'):
        # OpenAI-style response
        prompt_tokens = getattr(response.usage, 'prompt_tokens', prompt_tokens)
        completion_tokens = getattr(response.usage, 'completion_tokens', completion_tokens)
    elif response and hasattr(response, 'response_metadata'):
        # Some LangChain responses
        metadata = response.response_metadata
        prompt_tokens = metadata.get('prompt_tokens', prompt_tokens)
        completion_tokens = metadata.get('completion_tokens', completion_tokens)
    
    # Estimate tokens if not available (rough approximation: 1 token ≈ 4 chars)
    if prompt_tokens == 0 and completion_tokens == 0 and response:
        if hasattr(response, 'content'):
            completion_tokens = len(response.content) // 4
    
    tracker.log_llm_call(
        node_name=node_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model,
        purpose=purpose
    )


def track_search_call(node_name: str, 
                     query: str = "",
                     num_results: int = 0) -> None:
    """
    Helper to track Tavily search API call.
    
    Usage:
        results = tavily_search(query, max_results=5)
        track_search_call("viral_posts_fetch", query, len(results))
    """
    tracker = get_usage_tracker()
    tracker.log_search_call(
        node_name=node_name,
        query=query,
        num_results=num_results
    )
