"""
LinkedIn Content Agent — LangGraph Pipeline.

Flow:
    input_node → input_refinement → style_memory_fetch → viral_posts_fetch → trend_discovery
    → claim_extraction → fact_verification → research_quality → source_query_generator
    → targeted_research → claim_extraction → fact_verification → contradiction_node → angle_builder
    → pov_builder → hook_generator
    → post_writer → engagement_optimizer → viral_scorer
    → store_post → human_approval → linkedin_publish → END

Supports:
    - Human-in-the-loop approval (interrupt_before=["human_approval"])
    - Regeneration loop (approval_status=="regenerate" → hook_generator)
    - Auto-iteration loop until target score (viral_scorer → hook_generator)
    - Auto-publish bypass
"""

import os

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from brain.linkedin.state import LinkedInAgentState
from brain.linkedin.nodes import (
    input_node,
    input_refinement_node,
    style_memory_fetch_node,
    viral_posts_fetch_node,
    trend_discovery_node,
    claim_extraction_node,
    fact_verification_node,
    research_quality_node,
    source_query_generator_node,
    targeted_research_node,
    contradiction_node,
    angle_builder_node,
    pov_builder_node,
    hook_generator_node,
    post_writer_node,
    engagement_optimizer_node,
    viral_scorer_node,
    store_post_node,
    human_approval_node,
    linkedin_publish_node,
)


def _research_router(state: dict) -> str:
    """
    Route after fact verification:
    - if research_confidence >= 0.6 AND research_realism_score >= 0.6 OR retries exhausted -> contradiction
    - else -> trend_discovery (research again)
    """
    confidence = float(state.get("research_confidence", 0.0) or 0.0)
    realism = float(state.get("research_realism_score", 0.0) or 0.0)
    retries = int(state.get("research_retry_count", 0) or 0)
    max_retries = int(os.getenv("LINKEDIN_MAX_RESEARCH_RETRIES", "3"))

    print(f"[RESEARCH ROUTER] confidence={confidence}, realism={realism}, retries={retries}/{max_retries}")

    status = (state.get("approval_status", "") or "").strip().lower()
    if status in {"aborted", "rejected"}:
        return "end"

    if confidence >= 0.6 and realism >= 0.6:
        return "contradiction"
    if retries >= max_retries:
        return "end"
    return "source_query_generator"


def _post_writer_router(state: dict) -> str:
    """
    Route after post writer:
    - rejected/aborted/error -> END
    - otherwise -> engagement_optimizer
    """
    status = (state.get("approval_status", "") or "").strip().lower()
    error = str(state.get("error", "") or "").strip()
    if status in {"aborted", "rejected"}:
        return "end"
    if error:
        return "end"
    return "engagement_optimizer"


def _approval_router(state: dict) -> str:
    """
    Route after human_approval node based on approval_status.
    - "approved" or auto_publish → linkedin_publish
    - "regenerate" → hook_generator (re-create from hooks onward)
    - "rejected" or anything else → END
    """
    status = state.get("approval_status", "")
    auto_publish = state.get("auto_publish", False)

    print(f"[ROUTER DEBUG] approval_status={status}, auto_publish={auto_publish}")

    if status == "approved" or (auto_publish and status == "awaiting"):
        print(f"[ROUTER DEBUG] returning: linkedin_publish")
        return "linkedin_publish"
    elif status == "regenerate":
        print(f"[ROUTER DEBUG] returning: hook_generator")
        return "hook_generator"
    else:
        print(f"[ROUTER DEBUG] returning: end")
        return "end"


def _score_router(state: dict) -> str:
    """
    Route after viral_scorer:
    - score >= target OR max iterations reached → store_post
    - else → hook_generator (iterate with scorer feedback)
    """
    target = float(os.getenv("LINKEDIN_TARGET_VIRAL_SCORE", "8.5"))
    max_iters = int(os.getenv("LINKEDIN_MAX_AUTO_ITERATIONS", "6"))

    score = float(state.get("viral_score", 0.0) or 0.0)
    iters = int(state.get("iteration_count", 0) or 0)
    status = (state.get("approval_status", "") or "").strip().lower()

    if status in {"aborted", "rejected"}:
        print("[SCORE ROUTER] returning: end (aborted/rejected)")
        return "end"

    print(f"[SCORE ROUTER] score={score}, target={target}, iteration={iters}/{max_iters}")

    if score >= target:
        print("[SCORE ROUTER] returning: store_post (target met or exceeded)")
        return "store_post"

    if iters >= max_iters:
        print("[SCORE ROUTER] returning: store_post (max iterations reached)")
        return "store_post"

    print("[SCORE ROUTER] returning: hook_generator (iterate)")
    return "hook_generator"


def build_linkedin_agent():
    """
    Build and compile the LinkedIn content generation LangGraph.
    Returns a compiled graph with MemorySaver checkpointer.
    """
    memory = MemorySaver()
    graph = StateGraph(LinkedInAgentState)

    # ==========================================
    # ADD NODES
    # ==========================================
    graph.add_node("input_node", input_node)
    graph.add_node("input_refinement", input_refinement_node)
    graph.add_node("style_memory_fetch", style_memory_fetch_node)
    graph.add_node("viral_posts_fetch", viral_posts_fetch_node)
    graph.add_node("trend_discovery", trend_discovery_node)
    graph.add_node("claim_extraction", claim_extraction_node)
    graph.add_node("fact_verification", fact_verification_node)
    graph.add_node("research_quality", research_quality_node)
    graph.add_node("source_query_generator", source_query_generator_node)
    graph.add_node("targeted_research", targeted_research_node)
    graph.add_node("contradiction", contradiction_node)
    graph.add_node("angle_builder", angle_builder_node)
    graph.add_node("pov_builder", pov_builder_node)
    graph.add_node("hook_generator", hook_generator_node)
    graph.add_node("post_writer", post_writer_node)
    graph.add_node("engagement_optimizer", engagement_optimizer_node)
    graph.add_node("viral_scorer", viral_scorer_node)
    graph.add_node("store_post", store_post_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("linkedin_publish", linkedin_publish_node)

    # ==========================================
    # SET ENTRY POINT
    # ==========================================
    graph.set_entry_point("input_node")

    # ==========================================
    # SEQUENTIAL EDGES
    # ==========================================
    graph.add_edge("input_node", "input_refinement")
    graph.add_edge("input_refinement", "style_memory_fetch")
    graph.add_edge("style_memory_fetch", "viral_posts_fetch")
    graph.add_edge("viral_posts_fetch", "trend_discovery")
    graph.add_edge("trend_discovery", "claim_extraction")
    graph.add_edge("claim_extraction", "fact_verification")
    graph.add_edge("source_query_generator", "targeted_research")
    graph.add_edge("targeted_research", "claim_extraction")
    graph.add_edge("contradiction", "angle_builder")
    graph.add_edge("angle_builder", "pov_builder")
    graph.add_edge("pov_builder", "hook_generator")
    graph.add_edge("hook_generator", "post_writer")
    graph.add_edge("fact_verification", "research_quality")
    graph.add_conditional_edges(
        "research_quality",
        _research_router,
        {
            "source_query_generator": "source_query_generator",
            "contradiction": "contradiction",
            "end": END,
        },
    )

    graph.add_conditional_edges(
        "post_writer",
        _post_writer_router,
        {
            "engagement_optimizer": "engagement_optimizer",
            "end": END,
        },
    )
    graph.add_edge("engagement_optimizer", "viral_scorer")
    graph.add_edge("store_post", "human_approval")

    # Score-based auto-iteration loop
    graph.add_conditional_edges(
        "viral_scorer",
        _score_router,
        {
            "store_post": "store_post",
            "hook_generator": "hook_generator",
            "end": END,
        },
    )

    # ==========================================
    # CONDITIONAL EDGE AFTER HUMAN APPROVAL
    # ==========================================
    graph.add_conditional_edges(
        "human_approval",
        _approval_router,
        {
            "linkedin_publish": "linkedin_publish",
            "hook_generator": "hook_generator",
            "end": END,
        },
    )

    # ==========================================
    # TERMINAL EDGE
    # ==========================================
    graph.add_edge("linkedin_publish", END)

    # ==========================================
    # COMPILE WITH CHECKPOINTER + INTERRUPT
    # ==========================================
    return graph.compile(
        checkpointer=memory,
        interrupt_before=["human_approval"],
    )
