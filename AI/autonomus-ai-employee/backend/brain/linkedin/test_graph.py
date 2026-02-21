"""
Tests for LinkedIn graph routing guards.

Run:
    cd backend && python -m pytest brain/linkedin/test_graph.py -v
"""

from brain.linkedin.graph import _research_router, _post_writer_router, _score_router


def test_research_router_ends_when_retries_exhausted_and_low_quality(monkeypatch):
    monkeypatch.setenv("LINKEDIN_MAX_RESEARCH_RETRIES", "1")
    state = {
        "research_confidence": 0.2,
        "research_realism_score": 0.49,
        "research_retry_count": 1,
        "approval_status": "",
    }
    assert _research_router(state) == "end"


def test_post_writer_router_ends_on_rejection():
    state = {
        "approval_status": "rejected",
        "error": "rejected_due_to_low_realism:0.49",
    }
    assert _post_writer_router(state) == "end"


def test_score_router_ends_on_abort():
    state = {
        "approval_status": "aborted",
        "viral_score": 9.9,
        "iteration_count": 0,
    }
    assert _score_router(state) == "end"
