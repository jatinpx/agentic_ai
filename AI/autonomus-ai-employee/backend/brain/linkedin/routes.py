"""
LinkedIn Content Agent — FastAPI Routes.

Endpoints:
    POST /linkedin/generate        — Generate a LinkedIn post (stops at approval)
    POST /linkedin/approve         — Approve/regenerate/reject a post
    GET  /linkedin/posts           — List all generated posts
    GET  /linkedin/posts/{post_id} — Get a specific post
    GET  /linkedin/auth/url        — Get LinkedIn OAuth2 authorization URL
    GET  /linkedin/auth/callback   — Handle OAuth2 callback
    GET  /linkedin/auth/status     — Check if LinkedIn is authenticated
"""

import uuid
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from brain.linkedin.models import PostInput, LinkedInApprovalRequest, LinkedInAuthCallback
from brain.linkedin.graph import build_linkedin_agent
from brain.logger import set_thread_id, clear_thread_id
from db.linkedin_repo import get_all_posts, get_post_by_id
from services.linkedin_api import (
    get_auth_url,
    exchange_code_for_token,
    is_authenticated,
    get_user_profile,
    get_access_token,
    validate_oauth_state,
)

# ==========================================
# ROUTER & GRAPH INSTANCE
# ==========================================

router = APIRouter(prefix="/linkedin", tags=["LinkedIn Content Agent"])

# Build the LinkedIn agent graph (separate from the main research agent)
linkedin_graph = build_linkedin_agent()


# ==========================================
# POST GENERATION
# ==========================================

@router.post("/generate")
async def generate_post(req: PostInput):
    """
    Start the LinkedIn post generation pipeline.
    Runs all nodes up to human_approval, then stops for approval.
    Returns thread_id and the generated post preview.
    """
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    set_thread_id(thread_id)

    initial_state = {
        "user_input": req.model_dump(),
        "topic": "",
        "tone": "",
        "audience": "",
        "goal": "",
        "include_emojis": False,
        "auto_publish": False,
        "style_examples": [],
        "viral_examples": [],
        "trends": "",
        "hooks": [],
        "selected_hook": "",
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

    try:
        linkedin_graph.invoke(initial_state, config)
    except Exception as e:
        clear_thread_id()
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")
    finally:
        clear_thread_id()

    # Get state after pipeline halted at human_approval
    current_state = linkedin_graph.get_state(config)
    values = current_state.values

    if values.get("error"):
        raise HTTPException(status_code=500, detail=str(values.get("error")))

    return {
        "thread_id": thread_id,
        "status": "awaiting_approval",
        "final_post": values.get("final_post", {}),
        "viral_score": values.get("viral_score", 0.0),
        "hooks": values.get("hooks", []),
        "selected_hook": values.get("selected_hook", ""),
        "trends": values.get("trends", ""),
        "post_id": values.get("post_id", ""),
    }


# ==========================================
# POST APPROVAL
# ==========================================

@router.post("/approve")
async def approve_post(req: LinkedInApprovalRequest):
    """
    Approve, regenerate, or reject a generated post.
    - approved: publishes (if LinkedIn token available)
    - regenerate: loops back to hook_generator for new content
    - rejected: ends the pipeline
    """
    config = {"configurable": {"thread_id": req.thread_id}}

    current_state = linkedin_graph.get_state(config)
    if not current_state.values:
        raise HTTPException(status_code=404, detail="Session not found")

    # Update state with approval decision
    update = {"approval_status": req.action}
    if req.edited_post:
        # User manually edited the post — update final_post content
        final_post = current_state.values.get("final_post", {})
        final_post["post"] = req.edited_post
        update["final_post"] = final_post

    if req.action == "regenerate":
        update["iteration_count"] = current_state.values.get("iteration_count", 0) + 1

    linkedin_graph.update_state(config, update)

    set_thread_id(req.thread_id)

    try:
        # Resume the graph - keep invoking until completion or next interrupt
        max_iterations = 10
        iteration = 0
        while iteration < max_iterations:
            result = linkedin_graph.invoke(None, config)
            state_snapshot = linkedin_graph.get_state(config)
            
            # Check if we hit another interrupt or completed
            if not state_snapshot.next or state_snapshot.next == ():
                break
            
            # If we're back at human_approval interrupt, stop
            if state_snapshot.next == ("human_approval",):
                break
                
            iteration += 1
    except Exception as e:
        clear_thread_id()
        raise HTTPException(status_code=500, detail=f"Approval processing failed: {e}")
    finally:
        clear_thread_id()

    # Get final state
    new_state = linkedin_graph.get_state(config)
    values = new_state.values
    next_node = new_state.next

    if values.get("error"):
        raise HTTPException(status_code=500, detail=str(values.get("error")))

    # Check if graph stopped again (regeneration → new approval needed)
    if next_node == ("human_approval",):
        return {
            "status": "awaiting_approval",
            "final_post": values.get("final_post", {}),
            "viral_score": values.get("viral_score", 0.0),
            "hooks": values.get("hooks", []),
            "selected_hook": values.get("selected_hook", ""),
            "post_id": values.get("post_id", ""),
            "iteration": values.get("iteration_count", 0),
        }

    # Pipeline completed
    return {
        "status": values.get("approval_status", "complete"),
        "final_post": values.get("final_post", {}),
        "publish_url": values.get("publish_url", ""),
        "viral_score": values.get("viral_score", 0.0),
        "post_id": values.get("post_id", ""),
    }


# ==========================================
# POST HISTORY
# ==========================================

@router.get("/posts")
async def list_posts(limit: int = Query(default=50, le=200)):
    """List all generated LinkedIn posts."""
    posts = get_all_posts(limit=limit)
    return {"posts": posts, "count": len(posts)}


@router.get("/posts/{post_id}")
async def get_post(post_id: str):
    """Get a specific LinkedIn post by ID."""
    post = get_post_by_id(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


# ==========================================
# LINKEDIN OAUTH2
# ==========================================

@router.get("/auth/url")
async def linkedin_auth_url():
    """Get the LinkedIn OAuth2 authorization URL to start the auth flow."""
    url = get_auth_url()
    return {
        "auth_url": url,
        "redirect_uri_note": "Ensure LINKEDIN_REDIRECT_URI points to your frontend callback: http://localhost:3000/api/linkedin/callback"
    }


@router.get("/auth/callback")
async def linkedin_auth_callback(code: str, state: Optional[str] = None):
    """
    Handle LinkedIn OAuth2 callback.
    Exchange the authorization code for an access token.
    """
    if not state or not validate_oauth_state(state):
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    result = exchange_code_for_token(code)
    if "error" in result:
        raise HTTPException(status_code=400, detail=f"OAuth2 failed: {result['error']}")

    return {
        "status": "authenticated",
        "access_token_preview": result.get("access_token", "")[:10] + "...",
        "expires_in": result.get("expires_in"),
    }


@router.get("/auth/status")
async def linkedin_auth_status():
    """Check if LinkedIn is currently authenticated."""
    token = get_access_token()
    if not token:
        return {"authenticated": False, "message": "No access token. Start OAuth2 flow."}

    authenticated = is_authenticated()
    if authenticated:
        profile = get_user_profile()
        return {
            "authenticated": True,
            "profile": {
                "name": profile.get("name", ""),
                "email": profile.get("email", ""),
            },
        }

    return {"authenticated": False, "message": "Token expired or invalid. Re-authenticate."}
