"""
LinkedIn Content Agent — LangGraph Pipeline.

Flow:
    input_node → style_memory_fetch → viral_posts_fetch → trend_research
    → hook_generator → post_writer → engagement_optimizer → viral_scorer
    → store_post → human_approval → linkedin_publish → END

Supports:
    - Human-in-the-loop approval (interrupt_before=["human_approval"])
    - Regeneration loop (approval_status=="regenerate" → hook_generator)
    - Auto-publish bypass
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from brain.linkedin.state import LinkedInAgentState
from brain.linkedin.nodes import (
    input_node,
    style_memory_fetch_node,
    viral_posts_fetch_node,
    trend_research_node,
    hook_generator_node,
    post_writer_node,
    engagement_optimizer_node,
    viral_scorer_node,
    store_post_node,
    human_approval_node,
    linkedin_publish_node,
)


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
    graph.add_node("style_memory_fetch", style_memory_fetch_node)
    graph.add_node("viral_posts_fetch", viral_posts_fetch_node)
    graph.add_node("trend_research", trend_research_node)
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
    graph.add_edge("input_node", "style_memory_fetch")
    graph.add_edge("style_memory_fetch", "viral_posts_fetch")
    graph.add_edge("viral_posts_fetch", "trend_research")
    graph.add_edge("trend_research", "hook_generator")
    graph.add_edge("hook_generator", "post_writer")
    graph.add_edge("post_writer", "engagement_optimizer")
    graph.add_edge("engagement_optimizer", "viral_scorer")
    graph.add_edge("viral_scorer", "store_post")
    graph.add_edge("store_post", "human_approval")

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
