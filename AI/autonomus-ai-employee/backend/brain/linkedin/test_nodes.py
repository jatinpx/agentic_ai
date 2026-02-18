"""
Tests for LinkedIn Content Agent nodes and graph.

Run:
    cd backend && python -m pytest brain/linkedin/test_nodes.py -v
"""

import pytest
from unittest.mock import patch, MagicMock
from brain.linkedin.models import PostInput
from brain.linkedin.state import LinkedInAgentState
from brain.linkedin.nodes import (
    input_node,
    style_memory_fetch_node,
    viral_posts_fetch_node,
    hook_generator_node,
    post_writer_node,
    engagement_optimizer_node,
    viral_scorer_node,
    store_post_node,
    human_approval_node,
    _parse_json_from_llm,
    _clean_think_tags,
)


# ==========================================
# HELPER: BASE STATE
# ==========================================

def make_base_state(**overrides) -> dict:
    """Create a minimal valid state dict for testing."""
    state = {
        "user_input": {"topic": "AI agents in 2026", "tone": "professional"},
        "topic": "AI agents in 2026",
        "tone": "professional",
        "audience": "tech professionals",
        "goal": "engagement",
        "include_emojis": False,
        "auto_publish": False,
        "style_examples": [],
        "viral_examples": [],
        "trends": "AI agents are trending in tech.",
        "hooks": [],
        "selected_hook": "Most people don't realize AI agents are about to replace SaaS.",
        "generated_post": {},
        "optimized_post": {},
        "viral_score": 0.0,
        "final_post": {},
        "post_id": "",
        "approval_status": "",
        "publish_url": "",
        "error": "",
        "iteration_count": 0,
    }
    state.update(overrides)
    return state


# ==========================================
# UNIT TESTS: UTILITIES
# ==========================================

class TestUtilities:
    def test_clean_think_tags(self):
        text = "Hello <think>internal reasoning</think> World"
        assert _clean_think_tags(text) == "Hello  World"

    def test_clean_think_tags_multiline(self):
        text = "Start <think>\nmulti\nline\n</think> End"
        assert _clean_think_tags(text) == "Start  End"

    def test_clean_think_tags_no_tags(self):
        text = "No tags here"
        assert _clean_think_tags(text) == "No tags here"

    def test_parse_json_from_llm_direct(self):
        text = '{"hook": "test", "post": "body"}'
        result = _parse_json_from_llm(text)
        assert result["hook"] == "test"
        assert result["post"] == "body"

    def test_parse_json_from_llm_code_block(self):
        text = '```json\n{"hook": "test"}\n```'
        result = _parse_json_from_llm(text)
        assert result["hook"] == "test"

    def test_parse_json_from_llm_with_think_tags(self):
        text = '<think>reasoning</think>```json\n{"hook": "test"}\n```'
        result = _parse_json_from_llm(text)
        assert result["hook"] == "test"

    def test_parse_json_from_llm_embedded(self):
        text = 'Here is the result: {"hook": "test", "score": 8} Done.'
        result = _parse_json_from_llm(text)
        assert result["hook"] == "test"

    def test_parse_json_from_llm_invalid(self):
        result = _parse_json_from_llm("not json at all")
        assert result == {}


# ==========================================
# UNIT TESTS: INPUT NODE
# ==========================================

class TestInputNode:
    def test_valid_input_dict(self):
        state = make_base_state(user_input={
            "topic": "AI replacing SaaS",
            "tone": "contrarian",
            "audience": "founders",
        })
        result = input_node(state)
        assert result["topic"] == "AI replacing SaaS"
        assert result["tone"] == "contrarian"
        assert result["audience"] == "founders"
        assert result["error"] == ""

    def test_valid_input_string(self):
        state = make_base_state(user_input="Remote work hot takes")
        result = input_node(state)
        assert result["topic"] == "Remote work hot takes"
        assert result["tone"] == "professional"  # default

    def test_defaults(self):
        state = make_base_state(user_input={"topic": "Test"})
        result = input_node(state)
        assert result["goal"] == "engagement"
        assert result["include_emojis"] is False
        assert result["auto_publish"] is False

    def test_empty_input(self):
        state = make_base_state(user_input={})
        result = input_node(state)
        assert "error" in result
        assert result["error"] != ""


# ==========================================
# UNIT TESTS: HUMAN APPROVAL NODE
# ==========================================

class TestHumanApprovalNode:
    def test_sets_awaiting(self):
        state = make_base_state()
        result = human_approval_node(state)
        assert result["approval_status"] == "awaiting"


# ==========================================
# UNIT TESTS: STYLE MEMORY FETCH (mocked)
# ==========================================

class TestStyleMemoryFetch:
    @patch("brain.linkedin.nodes.recall_memory")
    @patch("brain.linkedin.nodes.pick_memory_for_role")
    @patch("brain.linkedin.nodes.embed_text")
    @patch("brain.linkedin.nodes.search_similar_posts")
    def test_returns_style_examples(self, mock_search, mock_embed, mock_pick, mock_recall):
        mock_recall.return_value = [("past post about AI", 0.3)]
        mock_pick.return_value = ["past post about AI"]
        mock_embed.return_value = [0.1] * 1536
        mock_search.return_value = [{"content": "similar post", "distance": 0.4}]

        state = make_base_state()
        result = style_memory_fetch_node(state)
        assert "style_examples" in result
        assert len(result["style_examples"]) >= 1

    @patch("brain.linkedin.nodes.recall_memory", side_effect=Exception("DB error"))
    @patch("brain.linkedin.nodes.embed_text")
    @patch("brain.linkedin.nodes.search_similar_posts")
    def test_handles_memory_error(self, mock_search, mock_embed, mock_recall):
        mock_embed.return_value = [0.1] * 1536
        mock_search.return_value = []

        state = make_base_state()
        result = style_memory_fetch_node(state)
        assert "style_examples" in result


# ==========================================
# UNIT TESTS: HOOK GENERATOR (mocked LLM)
# ==========================================

class TestHookGenerator:
    @patch("brain.linkedin.nodes.chat")
    def test_generates_hooks(self, mock_chat):
        mock_chat.return_value = '''```json
{
  "hooks": [
    {"type": "curiosity", "text": "Most people miss this...", "strength_score": 8},
    {"type": "authority", "text": "After 10 years...", "strength_score": 7},
    {"type": "contrarian", "text": "Hot take:", "strength_score": 9},
    {"type": "storytelling", "text": "Last week I...", "strength_score": 6},
    {"type": "debate", "text": "Is AI overrated?", "strength_score": 7}
  ],
  "best_hook_index": 2,
  "reason": "Contrarian hooks drive comments"
}```'''
        state = make_base_state()
        result = hook_generator_node(state)
        assert len(result["hooks"]) == 5
        assert "Hot take:" in result["selected_hook"]

    @patch("brain.linkedin.nodes.chat", side_effect=Exception("LLM error"))
    def test_fallback_on_error(self, mock_chat):
        state = make_base_state()
        result = hook_generator_node(state)
        assert len(result["hooks"]) >= 1
        assert result["selected_hook"] != ""


# ==========================================
# UNIT TESTS: POST WRITER (mocked LLM)
# ==========================================

class TestPostWriter:
    @patch("brain.linkedin.nodes.chat")
    def test_writes_post(self, mock_chat):
        mock_chat.return_value = '''{"hook": "Test hook", "post": "Full post body here.", "cta": "What do you think?", "hashtags": ["AI", "Tech"], "viral_score_prediction": 7.5, "reasoning": "Strong hook"}'''
        state = make_base_state()
        result = post_writer_node(state)
        assert result["generated_post"]["post"] == "Full post body here."
        assert result["generated_post"]["hook"] == "Test hook"

    @patch("brain.linkedin.nodes.chat", side_effect=Exception("timeout"))
    def test_fallback_on_error(self, mock_chat):
        state = make_base_state()
        result = post_writer_node(state)
        assert "post" in result["generated_post"]
        assert len(result["generated_post"]["post"]) > 0


# ==========================================
# UNIT TESTS: VIRAL SCORER (mocked)
# ==========================================

class TestViralScorer:
    @patch("brain.linkedin.nodes.search_similar_posts", return_value=[])
    @patch("brain.linkedin.nodes.embed_text", return_value=[0.1] * 1536)
    @patch("brain.linkedin.nodes.chat")
    def test_scores_post(self, mock_chat, mock_embed, mock_search):
        mock_chat.return_value = '{"viral_score": 7.8, "breakdown": {"hook_strength": 1.8}, "reasoning": "Strong"}'
        state = make_base_state(optimized_post={"post": "test post", "reasoning": ""})
        result = viral_scorer_node(state)
        assert result["viral_score"] == 7.8

    @patch("brain.linkedin.nodes.search_similar_posts", return_value=[])
    @patch("brain.linkedin.nodes.embed_text", return_value=[0.1] * 1536)
    @patch("brain.linkedin.nodes.chat", side_effect=Exception("error"))
    def test_default_score_on_error(self, mock_chat, mock_embed, mock_search):
        state = make_base_state(optimized_post={"post": "test"})
        result = viral_scorer_node(state)
        assert result["viral_score"] == 5.0


# ==========================================
# UNIT TESTS: STORE POST (mocked DB)
# ==========================================

class TestStorePost:
    @patch("brain.linkedin.nodes.insert_post", return_value="uuid-123")
    @patch("brain.linkedin.nodes.embed_text", return_value=[0.1] * 1536)
    def test_stores_and_returns_id(self, mock_embed, mock_insert):
        state = make_base_state(
            optimized_post={
                "post": "Test post",
                "hook": "Hook",
                "cta": "Comment below",
                "hashtags": ["AI"],
                "reasoning": "test",
            },
            viral_score=7.5,
        )
        result = store_post_node(state)
        assert result["post_id"] == "uuid-123"
        assert result["final_post"]["hook"] == "Hook"
        mock_insert.assert_called_once()


# ==========================================
# PYDANTIC MODEL TESTS
# ==========================================

class TestPostInput:
    def test_defaults(self):
        m = PostInput(topic="test")
        assert m.tone == "professional"
        assert m.audience == "tech professionals"
        assert m.goal == "engagement"
        assert m.include_emojis is False
        assert m.auto_publish is False

    def test_custom_values(self):
        m = PostInput(
            topic="AI",
            tone="contrarian",
            audience="founders",
            goal="authority",
            include_emojis=True,
            auto_publish=True,
        )
        assert m.tone == "contrarian"
        assert m.auto_publish is True

    def test_topic_required(self):
        with pytest.raises(Exception):
            PostInput()
