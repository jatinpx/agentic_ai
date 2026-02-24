"""
News Aggregation Service

Fetches tech news from multiple sources (Tavily, DuckDuckGo, NewsAPI).
Deduplicates and filters for relevance to tech domain.
Returns structured news items ready for topic ranking.
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

try:
    import requests
except ImportError:
    requests = None


class NewsAggregator:
    """Fetches and aggregates tech news from multiple sources."""

    def __init__(self):
        self.tavily_client = None
        self.newsapi_key = os.getenv("NEWSAPI_KEY")
        
        # Initialize Tavily if API key exists
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key and TavilyClient:
            try:
                self.tavily_client = TavilyClient(api_key=tavily_key)
            except Exception as e:
                print(f"Warning: Tavily client initialization failed: {e}")

    async def fetch_tech_news(self, hours_back: int = 6) -> List[Dict[str, Any]]:
        """
        Fetch recent tech news from multiple sources.
        
        Args:
            hours_back: How many hours back to search (default: 24 hours)
            
        Returns:
            List of news items with structure:
            {
                "title": str,
                "headline": str,
                "source": str,
                "url": str,
                "published_date": str (ISO format),
                "category": str,  # "AI", "Startup", "Infrastructure", "Security", etc.
            }
        """
        hours_back = self._resolve_hours_back(hours_back)
        news_items = []

        # Fetch from each source
        tavily_news = await self._fetch_tavily()
        news_items.extend(tavily_news)

        # Keep only recent items, then deduplicate by headline similarity
        recent_items = self._filter_recent_news(news_items, hours_back)
        deduped = self._deduplicate_news(recent_items)

        return deduped

    def _resolve_hours_back(self, hours_back: int) -> int:
        """Resolve hours_back from env if set."""
        raw = os.getenv("NEWS_HOURS_BACK", "").strip()
        if raw:
            try:
                value = int(raw)
                if value > 0:
                    return value
            except ValueError:
                pass
        return hours_back

    def _filter_recent_news(self, items: List[Dict[str, Any]], hours_back: int) -> List[Dict[str, Any]]:
        """Filter out news items older than the hours_back window."""
        if hours_back <= 0:
            return items

        cutoff = datetime.now() - timedelta(hours=hours_back)
        filtered: List[Dict[str, Any]] = []

        for item in items:
            published = self._parse_published_date(item.get("published_date"))
            if not published or published >= cutoff:
                filtered.append(item)

        return filtered

    def _parse_published_date(self, raw_date: Optional[str]) -> Optional[datetime]:
        """Parse an ISO-like published_date into datetime."""
        if not raw_date:
            return None

        try:
            cleaned = raw_date.replace("Z", "+00:00")
            return datetime.fromisoformat(cleaned)
        except (ValueError, TypeError):
            return None

    async def _fetch_tavily(self) -> List[Dict[str, Any]]:
        """Fetch from Tavily Search API."""
        if not self.tavily_client:
            return []

        queries = [
            "latest AI LLM breakthroughs 2026",
            "tech startup funding announcements",
            "infrastructure DevOps Kubernetes",
            "cybersecurity threats vulnerabilities",
            "cloud computing AWS Azure",
            "web development frameworks libraries",
            "machine learning papers research",
        ]

        all_results = []

        for query in queries:
            try:
                response = self.tavily_client.search(
                    query=query,
                    max_results=5,
                    include_answer=False,
                    topic="news",
                )

                for result in response.get("results", []):
                    news_item = {
                        "title": result.get("title", ""),
                        "headline": result.get("title", ""),
                        "source": result.get("source", ""),
                        "url": result.get("url", ""),
                        "published_date": datetime.now().isoformat(),  # Tavily doesn't return date
                        "category": self._categorize_query(query),
                        "snippet": result.get("content", "")[:200],
                    }
                    all_results.append(news_item)
            except Exception as e:
                print(f"Error fetching from Tavily for query '{query}': {e}")

        return all_results

    async def _fetch_newsapi(self) -> List[Dict[str, Any]]:
        """Fetch from NewsAPI (requires API key)."""
        if not self.newsapi_key or not requests:
            return []

        url = "https://newsapi.org/v2/everything"
        keywords = ["AI", "startups", "tech", "DevOps", "cloud", "cryptocurrency"]

        all_results = []

        for keyword in keywords:
            try:
                params = {
                    "q": keyword,
                    "sortBy": "publishedAt",
                    "language": "en",
                    "pageSize": 5,
                    "apiKey": self.newsapi_key,
                }
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()

                data = response.json()

                for article in data.get("articles", []):
                    news_item = {
                        "title": article.get("title", ""),
                        "headline": article.get("title", ""),
                        "source": article.get("source", {}).get("name", ""),
                        "url": article.get("url", ""),
                        "published_date": article.get("publishedAt", datetime.now().isoformat()),
                        "category": keyword,
                        "snippet": article.get("description", "")[:200],
                    }
                    all_results.append(news_item)
            except Exception as e:
                print(f"Error fetching from NewsAPI for keyword '{keyword}': {e}")

        return all_results

    async def _fetch_hackernews(self) -> List[Dict[str, Any]]:
        """Fetch from Hacker News API (supplementary)."""
        if not requests:
            return []

        try:
            # Get top 30 stories
            stories_url = "https://hacker-news.firebaseio.com/v0/topstories.json"
            response = requests.get(stories_url, timeout=10)
            response.raise_for_status()
            story_ids = response.json()[:20]

            all_results = []

            for story_id in story_ids:
                try:
                    story_url = f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
                    story_response = requests.get(story_url, timeout=5)
                    story_response.raise_for_status()
                    story = story_response.json()

                    if story.get("type") == "story" and story.get("url"):
                        news_item = {
                            "title": story.get("title", ""),
                            "headline": story.get("title", ""),
                            "source": "Hacker News",
                            "url": story.get("url", ""),
                            "published_date": datetime.fromtimestamp(story.get("time", 0)).isoformat(),
                            "category": "Tech",
                            "snippet": "",
                        }
                        all_results.append(news_item)
                except Exception as e:
                    print(f"Error fetching Hacker News story {story_id}: {e}")

            return all_results
        except Exception as e:
            print(f"Error fetching from Hacker News: {e}")
            return []

    def _deduplicate_news(self, news_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate news items based on headline similarity."""
        if not news_items:
            return []

        # Simple deduplication: keep unique headlines
        seen_headlines = set()
        deduped = []

        for item in news_items:
            headline_lower = item.get("headline", "").lower().strip()
            if headline_lower and headline_lower not in seen_headlines:
                seen_headlines.add(headline_lower)
                deduped.append(item)

        return deduped[:50]  # Return top 50 unique items

    def _categorize_query(self, query: str) -> str:
        """Categorize a query into tech domain categories."""
        query_lower = query.lower()
        
        if "ai" in query_lower or "llm" in query_lower or "ml" in query_lower:
            return "AI/ML"
        elif "startup" in query_lower or "funding" in query_lower:
            return "Startups"
        elif "infrastructure" in query_lower or "devops" in query_lower or "kubernetes" in query_lower:
            return "Infrastructure"
        elif "security" in query_lower or "vulnerability" in query_lower:
            return "Security"
        elif "cloud" in query_lower:
            return "Cloud"
        elif "web" in query_lower or "framework" in query_lower:
            return "Web Dev"
        else:
            return "Tech"


# Global instance
news_aggregator = None


def get_news_aggregator() -> NewsAggregator:
    """Get or create global news aggregator instance."""
    global news_aggregator
    if news_aggregator is None:
        news_aggregator = NewsAggregator()
    return news_aggregator


# Synchronous wrapper for FastAPI
def fetch_tech_news_sync(hours_back: int = 24) -> List[Dict[str, Any]]:
    """Synchronous wrapper for fetching tech news (for scheduler compatibility)."""
    import asyncio
    
    aggregator = get_news_aggregator()
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(aggregator.fetch_tech_news(hours_back))
