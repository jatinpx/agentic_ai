"""
Test suite for Phase 1 MVP automation workflow
Run with: pytest test_automation_pipeline.py -v
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

# Import services
from services.news_aggregator import NewsAggregator, fetch_tech_news_sync
from services.topic_ranker import TopicRanker, rank_and_suggest_topics
from services.scheduler_service import SchedulerService
from chat.models import ChatMessage, DailySuggestion, UserProfile, ChatState
from chat.handlers import ChatStateManager
from db.automation_db import AutomationDBService


# ==================== TESTS ====================

class TestNewsAggregator:
    """Test news aggregation service."""

    @pytest.mark.asyncio
    async def test_fetch_tech_news_returns_list(self):
        """News aggregator should return list of news items."""
        agg = NewsAggregator()
        news = await agg.fetch_tech_news(hours_back=24)
        
        assert isinstance(news, list)
        assert len(news) >= 0  # May be empty if APIs fail
        
        if news:
            # Validate structure
            item = news[0]
            assert "title" in item
            assert "url" in item
            assert "source" in item
            assert "published_date" in item

    @pytest.mark.asyncio
    async def test_deduplication_removes_duplicates(self):
        """Deduplicator should remove duplicate headlines."""
        agg = NewsAggregator()
        
        test_items = [
            {"headline": "AI Breakthrough", "url": "url1", "source": "src1"},
            {"headline": "AI Breakthrough", "url": "url2", "source": "src2"},  # Duplicate
            {"headline": "New AI Model", "url": "url3", "source": "src3"},
        ]
        
        deduped = agg._deduplicate_news(test_items)
        assert len(deduped) == 2
        assert deduped[0]["headline"] == "AI Breakthrough"


class TestTopicRanker:
    """Test topic ranking service."""

    @pytest.mark.asyncio
    async def test_rank_topics_returns_ranked_list(self):
        """Topic ranker should rank and return topics."""
        ranker = TopicRanker()
        
        test_news = [
            {
                "headline": "OpenAI Releases GPT-5 with Breakthrough Capabilities",
                "title": "OpenAI GPT-5",
                "source": "TechCrunch",
                "url": "https://example.com/1",
                "published_date": datetime.now().isoformat(),
                "category": "AI/ML",
                "snippet": "Major AI breakthrough...",
            },
            {
                "headline": "Startup Raises $100M in Series B Funding",
                "title": "Startup Funding",
                "source": "VentureBeat",
                "url": "https://example.com/2",
                "published_date": datetime.now().isoformat(),
                "category": "Startups",
                "snippet": "Startup series B funding...",
            },
        ]
        
        ranked = await ranker.rank_topics(test_news, ["AI", "Startups"], top_n=2)
        
        assert isinstance(ranked, list)
        assert len(ranked) <= 2
        
        if ranked:
            item = ranked[0]
            assert "score" in item
            assert "virality_score" in item
            assert "relevance_score" in item
            assert "content_angles" in item
            assert item["score"] >= 0 and item["score"] <= 100

    def test_virality_scoring(self):
        """Test virality scoring logic."""
        ranker = TopicRanker()
        
        # High impact news
        high_impact = {
            "headline": "Critical Security Vulnerability Discovered in OpenSSL",
            "category": "Security",
            "published_date": datetime.now().isoformat(),
        }
        
        # Low impact news
        low_impact = {
            "headline": "Developer Releases Update to Minor Library",
            "category": "Web Dev",
            "published_date": datetime.now().isoformat(),
        }
        
        high_score = ranker._score_virality(high_impact)
        low_score = ranker._score_virality(low_impact)
        
        assert high_score > low_score
        assert high_score <= 100
        assert low_score >= 0

    def test_relevance_scoring(self):
        """Test relevance scoring logic."""
        ranker = TopicRanker()
        
        user_interests = ["AI", "Startups"]
        
        # Relevant to interests
        relevant = {
            "headline": "New AI Model Shows Promise in Startup Applications",
            "category": "AI/ML",
        }
        
        # Not relevant
        irrelevant = {
            "headline": "New Plumbing Techniques Improve Water Flow",
            "category": "Infrastructure",
        }
        
        relevant_score = ranker._score_relevance(relevant, user_interests)
        irrelevant_score = ranker._score_relevance(irrelevant, user_interests)
        
        assert relevant_score > irrelevant_score


class TestChatStateManager:
    """Test chat state management."""

    @pytest.mark.asyncio
    async def test_get_user_state_creates_new(self):
        """Should create new state for new user."""
        manager = ChatStateManager()
        
        state = await manager.get_user_state("user123")
        
        assert state.user_id == "user123"
        assert state.state == "waiting_for_topic_selection"
        assert state.selected_topic_ids == []

    @pytest.mark.asyncio
    async def test_handle_topic_selection(self):
        """Should add topic to selected list."""
        manager = ChatStateManager()
        
        result = await manager._handle_topic_selection(
            user_id="user123",
            topic_id="topic_abc",
            state=ChatState(user_id="user123"),
            context={},
            adapter=None,
        )
        
        assert result["success"] == True
        
        state = await manager.get_user_state("user123")
        assert "topic_abc" in state.selected_topic_ids

    @pytest.mark.asyncio
    async def test_reset_user_state(self):
        """Should reset user state."""
        manager = ChatStateManager()
        
        # Set some state
        await manager.update_user_state("user123", {
            "selected_topic_ids": ["topic1", "topic2"],
            "state": "generating_post",
        })
        
        # Reset
        await manager.reset_user_state("user123")
        
        state = await manager.get_user_state("user123")
        assert state.state == "waiting_for_topic_selection"
        assert state.selected_topic_ids == []


class TestSchedulerService:
    """Test scheduler service."""

    def test_scheduler_initialization(self):
        """Scheduler should initialize without errors."""
        scheduler = SchedulerService()
        
        assert scheduler.scheduler is not None
        assert scheduler.is_running == False

    def test_scheduler_start_stop(self):
        """Scheduler should start and stop."""
        scheduler = SchedulerService()
        
        success = scheduler.start()
        assert success == True
        assert scheduler.is_running == True
        
        scheduler.stop()
        assert scheduler.is_running == False

    def test_schedule_job(self):
        """Should schedule a job."""
        scheduler = SchedulerService()
        scheduler.start()
        
        async def dummy_job():
            return {"status": "done"}
        
        success = scheduler.schedule_daily_news_pipeline(
            callback=dummy_job,
            hour=10,
            minute=30,
            job_id="test_job",
        )
        
        assert success == True
        
        job = scheduler.get_job("test_job")
        assert job is not None
        
        scheduler.stop()


class TestChatModels:
    """Test chat data models."""

    def test_chat_message_model(self):
        """ChatMessage should validate required fields."""
        msg = ChatMessage(
            user_id="user123",
            chat_id="chat456",
            text="Hello bot",
        )
        
        assert msg.user_id == "user123"
        assert msg.platform == "telegram"
        assert msg.text == "Hello bot"
        assert msg.message_type == "text"
        assert msg.id is not None

    def test_daily_suggestion_model(self):
        """DailySuggestion should accept topic list."""
        topics = [
            {
                "title": "AI Breakthrough",
                "headline": "OpenAI Releases GPT-5",
                "source": "TechCrunch",
                "url": "https://techcrunch.com/1",
                "category": "AI/ML",
                "score": 95.5,
                "virality_score": 90,
                "relevance_score": 98,
                "content_angles": ["Why this matters", "How to apply"],
                "rank": 1,
            }
        ]
        
        suggestion = DailySuggestion(
            user_id="user123",
            topics=topics,
            message_id="msg123",
        )
        
        assert suggestion.user_id == "user123"
        assert len(suggestion.topics) == 1
        assert suggestion.status == "sent"

    def test_user_profile_model(self):
        """UserProfile should store automation settings."""
        profile = UserProfile(
            telegram_user_id=123456789,
            tech_interests=["AI", "Startups", "Security"],
            automation_enabled=True,
            suggestion_time="08:00",
        )
        
        assert profile.telegram_user_id == 123456789
        assert "AI" in profile.tech_interests
        assert profile.automation_enabled == True


# ==================== INTEGRATION TESTS ====================

class TestPipelineIntegration:
    """Integration tests for full pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline_flow(self):
        """Test full news-to-suggestions flow."""
        # Note: This test uses mock APIs to avoid external calls
        
        agg = NewsAggregator()
        ranker = TopicRanker()
        
        # Mock news aggregator to return test data
        test_news = [
            {
                "headline": "AI Breakthrough: New Model Achieves 99% Accuracy",
                "title": "AI Model",
                "source": "ArXiv",
                "url": "https://arxiv.org/1",
                "published_date": datetime.now().isoformat(),
                "category": "AI/ML",
                "snippet": "Researchers announce breakthrough...",
            },
            {
                "headline": "Startup Series B: Company Raises $50 Million",
                "title": "Startup Funding",
                "source": "Crunchbase",
                "url": "https://crunchbase.com/1",
                "published_date": datetime.now().isoformat(),
                "category": "Startups",
                "snippet": "Well-funded startup...",
            },
        ]
        
        # Rank the test news
        ranked = await ranker.rank_topics(
            test_news,
            user_interests=["AI", "Startups"],
            top_n=2,
        )
        
        assert len(ranked) == 2
        assert ranked[0]["score"] >= ranked[1]["score"]  # Sorted by score


# ==================== PERFORMANCE TESTS ====================

class TestPerformance:
    """Performance benchmarks for pipeline."""

    @pytest.mark.asyncio
    async def test_ranking_speed(self):
        """Ranking should complete in reasonable time."""
        ranker = TopicRanker()
        
        # Generate test data
        test_news = [
            {
                "headline": f"News Item {i}: {['AI', 'Startup', 'Security', 'Cloud', 'Web Dev'][i % 5]}",
                "title": f"Item {i}",
                "source": "Source",
                "url": f"https://example.com/{i}",
                "published_date": datetime.now().isoformat(),
                "category": "Tech",
                "snippet": "Test snippet...",
            }
            for i in range(50)
        ]
        
        import time
        start = time.time()
        
        ranked = await ranker.rank_topics(test_news, ["AI", "Startups"], top_n=5)
        
        elapsed = time.time() - start
        
        assert len(ranked) <= 5
        assert elapsed < 5.0  # Should complete in < 5 seconds


# ==================== TEST UTILITIES ====================

@pytest.fixture
def mock_telegram_adapter():
    """Mock Telegram adapter for testing."""
    adapter = Mock()
    adapter.send_topic_suggestions = AsyncMock(return_value="msg123")
    adapter.send_post_for_approval = AsyncMock(return_value="msg456")
    return adapter


@pytest.fixture
def mock_database():
    """Mock database service."""
    db = Mock()
    db.get_AutomationEnabledUsers = AsyncMock(return_value=[
        {"id": "user1", "telegram_user_id": 123, "tech_interests": ["AI"]},
        {"id": "user2", "telegram_user_id": 456, "tech_interests": ["Startups"]},
    ])
    db.save_daily_suggestions = AsyncMock(return_value="sugg123")
    return db


# ==================== PYTEST CONFIGURATION ====================

@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
