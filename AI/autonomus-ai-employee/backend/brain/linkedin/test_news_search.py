"""
Tests for news discovery and topic search reliability nodes.
Verifies parallel search orchestration, fallback logic, and async consistency.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
import os

from brain.linkedin.nodes import (
    trend_discovery_node,
    fact_verification_node,
    targeted_research_node,
    contradiction_node
)

# ==========================================
# TEST DATA
# ==========================================

MOCK_PERSONA = {
    "identity": {
        "industry": "Artificial Intelligence",
        "job_role": "AI Engineer"
    },
    "technical": {
        "tech_stack": ["Python", "FastAPI"]
    }
}

MOCK_SEARCH_RESULT = {
    "count": 2,
    "results": [
        {
            "url": "https://techcrunch.com/news-1",
            "title": "Major AI Funding",
            "content": "A startup raised $50M for foundation models.",
            "published_date": "2024-02-15"
        },
        {
            "url": "https://reuters.com/ai-update",
            "title": "Open Source Breakthrough",
            "content": "New framework cuts training costs by 40%.",
            "published_date": "2024-02-18"
        }
    ]
}

EMPTY_SEARCH_RESULT = {"count": 0, "results": []}

# ==========================================
# ASYNC NODE TESTS
# ==========================================

@pytest.mark.asyncio
async def test_trend_discovery_success():
    """Test trend_discovery_node with successful search."""
    state = {
        "topic": "AI agents",
        "user_persona": MOCK_PERSONA,
        "research_retry_count": 0
    }

    # Mock tavily_search_structured to return 2 results for each of the 5 initial queries
    with patch("brain.linkedin.nodes.tavily_search_structured", return_value=MOCK_SEARCH_RESULT) as mock_search:
        result = await trend_discovery_node(state)
        
        # Initial 5 queries expected
        assert mock_search.call_count == 5
        assert "trend_candidates" in result
        assert len(result["trend_candidates"]) > 0
        assert result["trend_candidates"][0]["title"] == "Major AI Funding"
        assert "trends" in result

@pytest.mark.asyncio
async def test_trend_discovery_fallback():
    """Test trend_discovery_node triggers fallback search if first pass is empty."""
    state = {
        "topic": "Obscure Niche Tech",
        "user_persona": MOCK_PERSONA
    }

    # First 5 calls return empty, then fallback calls (3) return mocked results
    mock_responses = [EMPTY_SEARCH_RESULT] * 5 + [MOCK_SEARCH_RESULT] * 3
    
    with patch("brain.linkedin.nodes.tavily_search_structured", side_effect=mock_responses) as mock_search:
        result = await trend_discovery_node(state)
        
        # 5 initial + 3 fallback
        assert mock_search.call_count == 8
        assert "trend_candidates" in result
        assert len(result["trend_candidates"]) > 0

@pytest.mark.asyncio
async def test_fact_verification_parallelism():
    """Test fact_verification_node parallelizes multiple claim verifications."""
    claims = [
        {"claim": "Company X raised $100M", "type": "funding"},
        {"claim": "NVIDIA released B200", "type": "launch"},
        {"claim": "MMLU score hit 90%", "type": "benchmark"}
    ]
    state = {
        "topic": "Tech News",
        "extracted_claims": claims
    }

    with patch("brain.linkedin.nodes.tavily_search_structured", return_value=MOCK_SEARCH_RESULT) as mock_search:
        with patch("brain.linkedin.nodes.insert_research_snapshot"): # Avoid DB calls
            result = await fact_verification_node(state)
            
            # One search task per unique claim
            assert mock_search.call_count == 3
            assert len(result["verified_claims"]) > 0
            assert result["research_confidence"] > 0

@pytest.mark.asyncio
async def test_contradiction_parallelism():
    """Test contradiction_node parallelizes searches across verified claims."""
    verified = [
        {"claim": "LLMs are safe", "truth_score": 0.8},
        {"claim": "Scaling is the only path", "truth_score": 0.7}
    ]
    state = {
        "topic": "AI Safety",
        "verified_claims": verified
    }

    with patch("brain.linkedin.nodes.tavily_search_structured", return_value=MOCK_SEARCH_RESULT) as mock_search:
        result = await contradiction_node(state)
        
        # 3 queries per claim (as defined in node)
        assert mock_search.call_count == 6
        assert "counter_claims" in result

@pytest.mark.asyncio
async def test_targeted_research_success():
    """Test targeted_research_node merges results correctly."""
    state = {
        "topic": "AI",
        "research_queries": ["query1", "query2"],
        "trend_candidates": [{"source": "existing-url"}]
    }

    with patch("brain.linkedin.nodes.tavily_search_structured", return_value=MOCK_SEARCH_RESULT) as mock_search:
        result = await targeted_research_node(state)
        
        assert mock_search.call_count == 2
        assert len(result["trend_candidates"]) > 1

@pytest.mark.parametrize("claim,expected", [
    ("Our internal benchmark shows 95% accuracy", True),
    ("Company claims their latency is 5ms", True),
    ("According to our in-house scores, we are faster", True),
    ("We achieved a score of 85 on MMLU", False), # Industry standard
    ("The models score on GSM8K was impressive", False), # Industry standard
    ("We announced the results of HumanEval", False), # Industry standard
    ("A press release about the new model", False), # No benchmark marker
    ("Benchmark results for Company X in industry report", False), # No self marker
])
def test_self_benchmark_logic(claim, expected):
    """Test the refined self-benchmark detection logic."""
    from brain.linkedin.nodes import _is_self_benchmark_claim
    assert _is_self_benchmark_claim(claim) == expected

if __name__ == "__main__":
    # Integration smoke test if run directly
    print("Run with: pytest brain/linkedin/test_news_search.py")
