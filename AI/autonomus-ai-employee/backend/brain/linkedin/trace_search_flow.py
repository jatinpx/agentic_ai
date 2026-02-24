"""
Diagnostic script to trace the entire Search & Verification flow.
Shows exact input/output data as it passes between nodes.
"""

import asyncio
import json
from unittest.mock import patch, MagicMock
from typing import Any, Dict

# Import the nodes we want to trace
from brain.linkedin.nodes import (
    trend_discovery_node,
    claim_extraction_node,
    fact_verification_node,
    contradiction_node,
    targeted_research_node
)

# --- Mock Data ---

MOCK_PERSONA = {
    "identity": {"industry": "AI/L Cap", "job_role": "Platform Engineer"},
    "technical": {"tech_stack": ["Kubernetes", "Rust"]}
}

MOCK_TAVILY_RESPONSE = {
    "count": 2,
    "results": [
        {
            "url": "https://example.com/breaking-news",
            "title": "Rust-based K8s Controller hits 1M reqs/sec",
            "content": "A new benchmark shows Rust controllers outperforming Go by 4x in high-scale K8s environments.",
            "published_date": "2024-02-20"
        }
    ]
}

MOCK_EXTRACTED_CLAIMS = {
    "claims": [
        {
            "claim": "Rust controllers outperform Go by 4x in high-scale K8s",
            "type": "performance",
            "verifiable": "strong",
            "source": "https://example.com/breaking-news"
        }
    ]
}

# --- Instrumentation Functions ---

def print_separator(title: str):
    print(f"\n{'='*20} {title.upper()} {'='*20}")

def log_io(node_name: str, inputs: Dict[str, Any], outputs: Dict[str, Any]):
    print(f"\n[NODE: {node_name}]")
    print(f"--- INPUT KEYS: {list(inputs.keys())}")
    if "topic" in inputs: print(f"    Topic: {inputs['topic']}")
    
    print(f"--- OUTPUT KEYS: {list(outputs.keys())}")
    if "trend_candidates" in outputs:
        print(f"    Extracted {len(outputs['trend_candidates'])} raw signals.")
    if "extracted_claims" in outputs:
        print(f"    Extracted {len(outputs['extracted_claims'])} structured claims.")
    if "verified_claims" in outputs:
        print(f"    Verified {len(outputs['verified_claims'])} claims.")
        for c in outputs["verified_claims"]:
            print(f"      - Claim: {c['claim'][:50]}... | Confidence: {c['claim_confidence']}")
    if "counter_claims" in outputs:
        print(f"    Found {len(outputs['counter_claims'])} contradictions.")

async def trace_flow():
    state = {
        "topic": "Rust for Kubernetes infrastructure",
        "user_persona": MOCK_PERSONA,
        "research_retry_count": 0
    }

    print_separator("Start Search Flow Trace")

    # 1. Trend Discovery
    with patch("brain.linkedin.nodes.tavily_search_structured", return_value=MOCK_TAVILY_RESPONSE):
        print("\nNode 1: trend_discovery_node (Async)")
        outputs = await trend_discovery_node(state)
        log_io("trend_discovery", state, outputs)
        state.update(outputs)

    # 2. Claim Extraction (Mocking LLM)
    with patch("brain.linkedin.nodes.chat", return_value=json.dumps(MOCK_EXTRACTED_CLAIMS)):
        print("\nNode 2: claim_extraction_node (Sync)")
        outputs = claim_extraction_node(state)
        log_io("claim_extraction", state, outputs)
        state.update(outputs)

    # 3. Fact Verification
    with patch("brain.linkedin.nodes.tavily_search_structured", return_value=MOCK_TAVILY_RESPONSE):
        with patch("brain.linkedin.nodes.insert_research_snapshot"):
            print("\nNode 3: fact_verification_node (Async)")
            outputs = await fact_verification_node(state)
            log_io("fact_verification", state, outputs)
            state.update(outputs)

    # 4. Contradiction Logic
    with patch("brain.linkedin.nodes.tavily_search_structured", return_value=MOCK_TAVILY_RESPONSE):
        print("\nNode 4: contradiction_node (Async)")
        outputs = await contradiction_node(state)
        log_io("contradiction", state, outputs)
        state.update(outputs)

    print_separator("Final State Result")
    # print(json.dumps(state, indent=2, default=str)) # Truncated for readability

if __name__ == "__main__":
    asyncio.run(trace_flow())
