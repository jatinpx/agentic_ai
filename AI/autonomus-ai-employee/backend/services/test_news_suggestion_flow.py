"""
Diagnostic script to trace the News Suggestion flow.
Fetches news via NewsAggregator and ranks them via TopicRanker to suggest 5 topics.
"""

import asyncio
import json
import os
from unittest.mock import patch, MagicMock
from datetime import datetime

# Import the services
from services.news_aggregator import NewsAggregator
from services.topic_ranker import TopicRanker

# --- Mock Data ---

MOCK_TAVILY_NEWS = [
    {
        "title": "OpenAI announces GPT-5 Preview",
        "url": "https://techcrunch.com/openai-gpt5",
        "content": "OpenAI has officially unveiled the preview of GPT-5, showing massive gains in reasoning and multi-modal understanding.",
        "source": "TechCrunch"
    },
    {
        "title": "Anthropic raises $2B from Amazon",
        "url": "https://reuters.com/anthropic-funding",
        "content": "Anthropic announced a new $2B funding round from Amazon to scale its Claude 3.5 Sonnet infrastructure.",
        "source": "Reuters"
    },
    {
        "title": "Mistral releases new open-source large model",
        "url": "https://mistral.ai/news/large-v2",
        "content": "Mistral Large v2 is now available, beating Llama 3 on several key benchmarks while remaining extremely efficient.",
        "source": "Mistral Blog"
    },
    {
        "title": "NVIDIA stock hits all-time high as AI demand soars",
        "url": "https://bloomberg.com/nvidia-stock",
        "content": "NVIDIA valuation continues to climb as cloud providers rush to secure H200 and B100 GPUs for next-gen clusters.",
        "source": "Bloomberg"
    },
    {
        "title": "New Kubernetes security vulnerability discovered",
        "url": "https://k8s.io/security-bulletin",
        "content": "A critical CVE in the Kubernetes API server could allow unauthorized access to secrets in multi-tenant environments.",
        "source": "K8s Security"
    },
    {
        "title": "FastAPI 1.0 released with native Pydantic v2 support",
        "url": "https://fastapi.tiangolo.com/release-1-0",
        "content": "FastAPI finally hits 1.0, bringing significant performance improvements and fully-baked support for Pydantic v2.",
        "source": "FastAPI Official"
    }
]

# --- Instrumentation Functions ---

def print_separator(title: str):
    print(f"\n{'='*20} {title.upper()} {'='*20}")

async def trace_news_suggestion_flow():
    user_interests = ["AI", "Startups", "Python", "Cloud"]
    
    print_separator("Start News Suggestion Flow Trace")
    print(f"User Interests: {user_interests}")

    # 1. News Aggregation
    aggregator = NewsAggregator()
    
    # Mocking Tavily output
    mock_tavily_response = {"results": MOCK_TAVILY_NEWS}
    
    with patch.object(aggregator, 'tavily_client') as mock_tavily:
        mock_tavily.search.return_value = mock_tavily_response
        
        print("\nStep 1: NewsAggregator.fetch_tech_news()")
        news_items = await aggregator.fetch_tech_news(hours_back=24)
        
        print(f"--- OUTPUT: {len(news_items)} news items aggregated.")
        for i, item in enumerate(news_items[:3]):
            print(f"    [{i+1}] {item.get('title')} ({item.get('source')})")

    # 2. Topic Ranking
    ranker = TopicRanker()
    
    # Mocking LLM for angle generation if needed, 
    # though ranker.rank_topics also uses embeddings and some internal scoring.
    # If ranker uses self.llm to generate "angles", we should mock it.
    
    mock_angles_response = [
        {"title": item.get('title'), "angle": f"Insight into {item.get('title')}", "relevance_reason": "High viral potential in tech."}
        for item in news_items
    ]

    print("\nStep 2: TopicRanker.rank_topics()")
    print(f"--- INPUT: {len(news_items)} items, interests={user_interests}")
    
    with patch.object(ranker, 'llm') as mock_llm:
        # Mocking the JSON response for angle generation
        mock_llm.invoke.return_value = json.dumps(["Business impact of this tech change", "Lessons for current startups", "Why this matters for your 2026 roadmap"])
        
        ranked_topics = await ranker.rank_topics(
            news_items,
            user_interests=user_interests,
            top_n=5
        )
        
        print(f"--- OUTPUT: {len(ranked_topics)} topics ranked and suggested.")
        for i, topic in enumerate(ranked_topics):
            score = topic.get('score', 'N/A')
            title = topic.get('title', 'Unknown')
            angles = topic.get('content_angles', [])
            angle = angles[0] if angles else "N/A"
            print(f"    [{i+1}] Score: {score} | {title}")
            print(f"        Suggested Angle: {angle}")

    print_separator("Final Suggested 5 Topics")
    for i, topic in enumerate(ranked_topics[:5]):
        print(f"{i+1}. {topic.get('title')}")

if __name__ == "__main__":
    # Ensure current dir is in PYTHONPATH if needed
    asyncio.run(trace_news_suggestion_flow())
