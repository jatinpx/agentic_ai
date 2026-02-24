"""
Topic Ranking Service

Scores news items by virality potential and relevance to target audience.
Generates unique LinkedIn content angles for top-ranked topics.
Uses LLM for relevance/angle generation.
"""

import json
from typing import List, Dict, Any, Tuple
from datetime import datetime
import os

try:
    from langchain_ollama import OllamaLLM
except ImportError:
    OllamaLLM = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    HuggingFaceEmbeddings = None


class TopicRanker:
    """Scores and ranks news topics by virality/relevance potential."""

    def __init__(self):
        self.llm = None
        self.embeddings = None
        self._init_llm()
        self._init_embeddings()

    def _init_llm(self):
        """Initialize LLM for angle generation (Gemini or Ollama)."""
        provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        
        # Try Gemini first (configured in .env)
        if provider == "gemini" and ChatGoogleGenerativeAI:
            try:
                api_key = os.getenv("GEMINI_API_KEY")
                if api_key:
                    self.llm = ChatGoogleGenerativeAI(
                        model="gemini-2.5-flash",
                        google_api_key=api_key,
                        temperature=0.7,
                    )
                    print("✓ Using Gemini LLM for angle generation")
                    return
            except Exception as e:
                print(f"Warning: Gemini LLM initialization failed: {e}")

        # Fallback to Ollama
        if OllamaLLM:
            try:
                ollama_host = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
                self.llm = OllamaLLM(
                    model="mistral",
                    base_url=ollama_host,
                    temperature=0.7,
                )
                print("✓ Using Ollama LLM for angle generation")
            except Exception as e:
                print(f"Warning: Ollama LLM initialization failed: {e}")

    def _init_embeddings(self):
        """Initialize embeddings for relevance scoring."""
        if not HuggingFaceEmbeddings:
            print("Warning: langchain_huggingface not installed")
            return

        try:
            self.embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
        except Exception as e:
            print(f"Warning: Embeddings initialization failed: {e}")

    async def rank_topics(
        self,
        news_items: List[Dict[str, Any]],
        user_interests: List[str] = None,
        top_n: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Rank news items by virality/relevance potential.
        
        Args:
            news_items: List of news items from aggregator
            user_interests: User's tech interests (e.g., ["AI", "Startups", "DevOps"])
            top_n: Number of top topics to return
            
        Returns:
            List of top-ranked topics with scores and generated angles:
            {
                "rank": int,
                "score": float (0-100),
                "title": str,
                "headline": str,
                "source": str,
                "url": str,
                "category": str,
                "published_date": str,
                "virality_score": float,
                "relevance_score": float,
                "content_angles": List[str],
                "reasoning": str,
            }
        """
        if not news_items:
            return []

        user_interests = user_interests or ["AI", "Startups", "Tech"]

        # Score each item
        scored_items = []
        for item in news_items:
            virality = self._score_virality(item)
            relevance = self._score_relevance(item, user_interests)
            combined = (virality * 0.6) + (relevance * 0.4)  # Weighted: virality 60%, relevance 40%

            # Generate content angles
            angles = await self._generate_angles(item)

            scored_item = {
                **item,
                "virality_score": round(virality, 2),
                "relevance_score": round(relevance, 2),
                "score": round(combined, 2),
                "content_angles": angles,
                "reasoning": self._explain_score(item, virality, relevance),
            }
            scored_items.append(scored_item)

        # Sort by score descending
        sorted_items = sorted(scored_items, key=lambda x: x["score"], reverse=True)

        # Add rank and return top N
        ranked = []
        for idx, item in enumerate(sorted_items[:top_n], 1):
            item["rank"] = idx
            ranked.append(item)

        return ranked

    def _score_virality(self, news_item: Dict[str, Any]) -> float:
        """
        Score virality potential (0-100).
        Factors: recency, impact keywords, source credibility, category.
        """
        score = 50.0  # Base score

        # Recency bonus: newer stories score higher
        pub_date_str = news_item.get("published_date", "")
        try:
            pub_date = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            hours_old = (datetime.now() - pub_date).total_seconds() / 3600
            if hours_old < 1:
                score += 30
            elif hours_old < 6:
                score += 20
            elif hours_old < 24:
                score += 10
        except ValueError:
            pass

        # Impact keywords boost
        headline = news_item.get("headline", "").lower()
        impact_keywords = [
            "breakthrough", "first", "new", "revolutionary", "trillion",
            "billion", "ipo", "partnership", "acquisition", "launch",
            "critical", "threat", "exploit", "vulnerability", "died",
        ]
        keyword_hits = sum(1 for kw in impact_keywords if kw in headline)
        score += min(keyword_hits * 5, 30)  # Max 30 points for keywords

        # Category virality weights
        category = news_item.get("category", "Tech").lower()
        category_weights = {
            "ai/ml": 25,
            "startups": 20,
            "security": 25,
            "cloud": 15,
            "infrastructure": 12,
            "web dev": 10,
        }
        score += category_weights.get(category, 10)

        # Unusual/sensational phrases
        sensational = ["chaos", "crisis", "emergency", "rare", "exclusive", "shocking"]
        sensational_hits = sum(1 for word in sensational if word in headline)
        score += min(sensational_hits * 3, 15)

        return min(score, 100.0)

    def _score_relevance(self, news_item: Dict[str, Any], user_interests: List[str]) -> float:
        """
        Score relevance to user interests (0-100).
        Factors: category match, keyword match in headline.
        """
        score = 0.0

        # Category match
        item_category = news_item.get("category", "").lower()
        for interest in user_interests:
            if interest.lower() in item_category:
                score += 40
                break
        else:
            # No exact match, check headline
            headline = news_item.get("headline", "").lower()
            for interest in user_interests:
                if interest.lower() in headline:
                    score += 25
                    break

        # Keyword expansion
        interest_keywords = {
            "AI": ["ai", "llm", "gpt", "model", "neural", "learning", "transformer"],
            "Startups": ["startup", "founded", "series", "seed", "vc", "funding", "raised"],
            "Security": ["security", "hack", "breach", "exploit", "vulnerability", "threat"],
            "Cloud": ["cloud", "aws", "azure", "gcp", "compute", "serverless"],
            "Infrastructure": ["infrastructure", "devops", "kubernetes", "docker", "deployment"],
            "Web Dev": ["web", "frontend", "backend", "react", "node", "framework"],
        }

        headline = news_item.get("headline", "").lower()
        for interest in user_interests:
            keywords = interest_keywords.get(interest, [])
            keyword_hits = sum(1 for kw in keywords if kw in headline)
            score += min(keyword_hits * 5, 30)

        return min(score, 100.0)

    async def _generate_angles(self, news_item: Dict[str, Any], angles_count: int = 3) -> List[str]:
        """
        Generate unique LinkedIn content angles for the news item.
        
        Uses LLM if available, falls back to template-based angles.
        Each angle is a brief (5-15 word) hook for LinkedIn post.
        """
        if not self.llm:
            return self._generate_template_angles(news_item, angles_count)

        headline = news_item.get("headline", "")
        snippet = news_item.get("snippet", "")[:300]  # Truncate context

        prompt = f"""Given this tech news headline and snippet, generate {angles_count} unique LinkedIn content angles.
Each angle should be 5-15 words, focusing on business impact, lessons learned, or industry implications.
Format: Return ONLY the angles as a JSON array, no other text.

Headline: {headline}
Snippet: {snippet}

Example format:
["angle 1 here", "angle 2 here", "angle 3 here"]"""

        try:
            response = self.llm.invoke(prompt)

            # Extract content from response (handle both AIMessage and string)
            import json
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Clean response (remove markdown code blocks if present)
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # Parse JSON response
            try:
                angles = json.loads(content)
                if isinstance(angles, list) and len(angles) > 0:
                    return angles[:angles_count]
            except json.JSONDecodeError:
                pass

        except Exception as e:
            print(f"Error generating angles with LLM: {e}")

        # Fallback to templates
        return self._generate_template_angles(news_item, angles_count)

    def _generate_template_angles(self, news_item: Dict[str, Any], angles_count: int = 3) -> List[str]:
        """Generate template-based angles if LLM is unavailable."""
        headline = news_item.get("headline", "")
        category = news_item.get("category", "Tech")

        templates = {
            "AI/ML": [
                f"Why {{action}} matters for AI capabilities",
                f"{{headline}} could reshape product development",
                f"The business case behind this {{category}} advancement",
            ],
            "Startups": [
                f"{{headline}} signals major shift in startup funding",
                f"Why this {{category}} move changes the game",
                f"The hidden opportunity in {{category}} consolidation",
            ],
            "Security": [
                f"Why {{headline}} matters for your infrastructure",
                f"{{category}} crisis: what you need to know today",
                f"The business impact of this {{category}} threat",
            ],
            "default": [
                f"Why {{headline}} is crucial for tech teams",
                f"{{category}}: the breakthrough you should care about",
                f"The future implications of this {{category}} development",
            ],
        }

        template_set = templates.get(category, templates["default"])
        angles = []

        for template in template_set[:angles_count]:
            angle = template.format(
                headline=headline[:30],
                action=headline.split()[0] if headline else "This",
                category=category,
            )
            angles.append(angle)

        return angles

    def _explain_score(self, news_item: Dict[str, Any], virality: float, relevance: float) -> str:
        """Generate brief explanation for why item was ranked."""
        category = news_item.get("category", "Tech")
        
        if virality > 75:
            virality_reason = "High virality potential"
        elif virality > 50:
            virality_reason = "Solid virality potential"
        else:
            virality_reason = "Moderate virality potential"

        if relevance > 75:
            relevance_reason = "Highly relevant to interests"
        elif relevance > 50:
            relevance_reason = "Relevant to your tech focus"
        else:
            relevance_reason = "Tangentially relevant"

        return f"{virality_reason} ({virality:.0f}/100) and {relevance_reason} ({relevance:.0f}/100)"


# Global instance
topic_ranker = None


def get_topic_ranker() -> TopicRanker:
    """Get or create global topic ranker instance."""
    global topic_ranker
    if topic_ranker is None:
        topic_ranker = TopicRanker()
    return topic_ranker


# High-level API
async def rank_and_suggest_topics(
    news_items: List[Dict[str, Any]],
    user_interests: List[str] = None,
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """
    Main entry point: rank news items and generate content angles.
    
    Usage from scheduler:
        from services.topic_ranker import rank_and_suggest_topics
        topics = await rank_and_suggest_topics(news_items, ["AI", "Startups"])
    """
    ranker = get_topic_ranker()
    return await ranker.rank_topics(news_items, user_interests, top_n)
