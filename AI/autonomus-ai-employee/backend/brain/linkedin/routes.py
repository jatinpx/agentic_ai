"""
LinkedIn Content Agent — FastAPI Routes.

Endpoints:
    GET  /linkedin/config           — Get configuration options for UI
    GET  /linkedin/profile-summary  — Get current user profile summary
    POST /linkedin/generate-with-config — Generate post with full UI config
    POST /linkedin/generate         — Generate a LinkedIn post (stops at approval)
    POST /linkedin/approve          — Approve/regenerate/reject a post
    POST /linkedin/abort            — Abort a running pipeline
    GET  /linkedin/posts            — List all generated posts
    GET  /linkedin/posts/{post_id}  — Get a specific post
    GET  /linkedin/auth/url         — Get LinkedIn OAuth2 authorization URL
    GET  /linkedin/auth/callback    — Handle OAuth2 callback
    GET  /linkedin/auth/status      — Check if LinkedIn is authenticated
    WS   /linkedin/ws/{thread_id}   — WebSocket for real-time pipeline updates
"""

import uuid
import asyncio
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, BackgroundTasks
from typing import Optional, Union

from brain.linkedin.models import PostInput, LinkedInApprovalRequest, LinkedInAuthCallback, PostGenerationRequest
from brain.linkedin.graph import build_linkedin_agent
from brain.logger import set_thread_id, clear_thread_id
from brain.linkedin.cancellation import request_abort, clear_abort, is_abort_requested, PipelineAborted
from db.linkedin_repo import get_all_posts, get_post_by_id
from brain.linkedin.websocket_manager import ws_manager
from services.linkedin_api import (
    get_auth_url,
    exchange_code_for_token,
    is_authenticated,
    get_user_profile,
    get_access_token,
    validate_oauth_state,
    get_configured_author_target,
)
from services.config_service import (
    get_configuration_options,
    merge_request_with_profile,
    get_profile_summary,
)

# ==========================================
# ROUTER & GRAPH INSTANCE
# ==========================================

router = APIRouter(prefix="/linkedin", tags=["LinkedIn Content Agent"])

# Build the LinkedIn agent graph (separate from the main research agent)
linkedin_graph = build_linkedin_agent()


# ==========================================
# BACKGROUND PIPELINE EXECUTION
# ==========================================

def run_linkedin_pipeline(thread_id: str, initial_state: dict):
    """
    Background task to run the LinkedIn pipeline asynchronously.
    This unblocks the HTTP request so other endpoints remain responsive.
    Progress is streamed via WebSocket to connected clients.
    """
    import time
    from brain.linkedin.logging_utils import log_agent_start, log_error
    from brain.linkedin.usage_tracker import init_usage_tracker, get_usage_tracker
    
    config = {"configurable": {"thread_id": thread_id}}
    set_thread_id(thread_id)
    clear_abort(thread_id)
    
    # Initialize usage tracking for this pipeline run
    init_usage_tracker()
    
    # Initialize iteration count
    from brain.logger import set_iteration_count
    set_iteration_count(0)
    
    # Small delay to allow WebSocket connection to establish
    time.sleep(0.5)
    
    # Broadcast pipeline start
    topic = initial_state.get("user_input", {}).get("topic", "unknown")
    log_agent_start(topic)
    
    try:
        # Invoke the pipeline - will stop at human_approval interrupt
        linkedin_graph.invoke(initial_state, config)
    except PipelineAborted:
        linkedin_graph.update_state(config, {
            "approval_status": "aborted",
            "error": "Pipeline aborted by user",
        })
        print(f"[LINKEDIN] Pipeline aborted cleanly for thread {thread_id}")
    except Exception as e:
        # Log error and broadcast via WebSocket
        log_error("pipeline", f"Pipeline execution failed: {e}")
    finally:
        # Get final usage stats with iteration count from state
        try:
            final_state = linkedin_graph.get_state(config)
            iteration = final_state.values.get("iteration_count", 0)
        except:
            iteration = 0
        
        tracker = get_usage_tracker()
        from brain.logger import set_iteration_count
        set_iteration_count(iteration)  # Update context for final summary
        usage_summary = tracker.get_summary()
        print(f"[USAGE] Pipeline completed: {usage_summary}")
        clear_abort(thread_id)
        clear_thread_id()


# ==========================================
# POST GENERATION
# ==========================================

@router.get("/config")
async def get_config():
    """
    Get all configuration options for UI form generation.
    
    Returns:
        Configuration schema with:
        - All available options for tone, format, audience, goal, cta_style, storytelling_frequency
        - Current defaults from user profile
        - Field descriptions and validation rules
        - User profile summary
    
    Usage:
        1. Call this endpoint to populate UI dropdowns
        2. Build PostGenerationRequest with selected values
        3. POST to /generate with the request
    """
    try:
        config = get_configuration_options()
        return config
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load configuration: {str(e)}")


@router.get("/profile-summary")
async def profile_summary():
    """
    Get a summary of the current user profile.
    
    Returns:
        User's identity, industries, tech stack, writing preferences, and career focus.
        This is displayed in the UI to show what profile defaults are being used.
    """
    try:
        summary = get_profile_summary()
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load profile: {str(e)}")


def validate_topic_quality(topic: str) -> tuple[bool, str]:
    """Validate topic quality before starting pipeline. Returns (is_valid, error_message)."""
    import re
    
    topic = topic.strip()
    if not topic:
        return False, "Topic cannot be empty. Please provide a meaningful topic."
    
    # Check basic quality
    topic_cleaned = re.sub(r"\s+", " ", topic)
    word_count = len(topic_cleaned.split())
    alpha_chars = sum(1 for ch in topic_cleaned if ch.isalpha())
    digit_ratio = sum(1 for ch in topic_cleaned if ch.isdigit()) / max(len(topic_cleaned), 1)
    
    # Reject single character or very short gibberish
    if word_count == 1 and len(topic_cleaned) < 3:
        return False, "Topic too short. Please write at least 2-3 words describing your topic (e.g., 'AI in healthcare', 'remote work trends')."
    
    # Reject if mostly digits or too few letters
    if digit_ratio > 0.5 or alpha_chars < 3:
        return False, "Topic unclear. Please use plain language to describe your topic (e.g., 'sustainable energy solutions', 'startup funding strategies')."
    
    # Warn if suspiciously short (1 word with 3+ chars)
    if word_count == 1:
        return False, "Topic is too vague. Please provide more context (e.g., instead of 'AI', write 'AI in education' or 'AI safety concerns')."
    
    return True, ""


@router.post("/generate")
async def generate_post(req: Union[PostGenerationRequest, PostInput], background_tasks: BackgroundTasks):
    """
    Start the LinkedIn post generation pipeline in the background.
    Returns thread_id immediately - connect to WebSocket for live updates.
    Pipeline runs all nodes up to human_approval, then stops for approval.
    
    Accepts either:
    - PostGenerationRequest: Optional override fields that merge with user profile defaults
    - PostInput: Full configuration (legacy format, backwards compatible)
    
    Usage:
        1. POST /generate with config → get thread_id
        2. Open WebSocket at /ws/{thread_id}
        3. Receive live status as pipeline runs
        4. POST /approve when ready
    """
    # Convert request to PostGenerationRequest if it's PostInput
    if isinstance(req, PostInput):
        # Legacy PostInput - convert to PostGenerationRequest for uniform handling
        gen_request = PostGenerationRequest(
            topic=req.topic,
            tone=req.tone,
            format=req.format,
            audience=req.audience,
            goal=req.goal,
            include_emojis=req.include_emojis,
            use_technical_jargon=req.use_technical_jargon,
            cta_style=req.cta_style,
            storytelling_frequency=req.storytelling_frequency,
        )
    else:
        gen_request = req
    
    # Merge request overrides with profile defaults
    resolved_config = merge_request_with_profile(gen_request)
    
    # Validate topic quality BEFORE starting pipeline
    is_valid, error_message = validate_topic_quality(resolved_config.topic)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)
    
    thread_id = str(uuid.uuid4())
    
    initial_state = {
        "user_input": resolved_config.model_dump(),
        "topic": "",
        "tone": "",
        "audience": "",
        "goal": "",
        "include_emojis": False,
        "auto_publish": False,
        "style_examples": [],
        "viral_examples": [],
        "trends": "",
        "trend_candidates": [],
        "extracted_claims": [],
        "verified_claims": [],
        "angle_package": {},
        "research_confidence": 0.0,
        "research_retry_count": 0,
        "hooks": [],
        "selected_hook": "",
        "generated_post": {},
        "optimized_post": {},
        "viral_score": 0.0,
        "realism_score": 0.0,
        "final_post": {},
        "post_id": "",
        "approval_status": "",
        "publish_url": "",
        "error": "",
        "iteration_count": 0,
        "score_feedback": {},
        "usage_stats": {
            "llm_calls": 0,
            "search_calls": 0,
            "total_api_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
    
    # Schedule pipeline to run in background
    background_tasks.add_task(run_linkedin_pipeline, thread_id, initial_state)
    
    # Return immediately with thread_id
    # Frontend should open WebSocket to /ws/{thread_id} for live updates
    return {
        "thread_id": thread_id,
        "status": "pipeline_starting",
        "message": "Connect to WebSocket at /linkedin/ws/{thread_id} for live updates",
        "websocket_url": f"/linkedin/ws/{thread_id}"
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
    if is_abort_requested(req.thread_id) or current_state.values.get("approval_status") == "aborted":
        raise HTTPException(status_code=409, detail="Pipeline already aborted")

    # Update state with approval decision
    # Clear stale non-fatal errors (e.g. prior publish_failed) so retries can proceed.
    update = {"approval_status": req.action, "error": ""}
    if req.edited_post:
        # User manually edited the post — update final_post content
        final_post = current_state.values.get("final_post", {})
        final_post["post"] = req.edited_post
        update["final_post"] = final_post

    if req.action == "regenerate":
        new_iteration = current_state.values.get("iteration_count", 0) + 1
        update["iteration_count"] = new_iteration
        
        # Update context variable for usage tracking
        from brain.logger import set_iteration_count
        set_iteration_count(new_iteration)

    linkedin_graph.update_state(config, update)

    set_thread_id(req.thread_id)

    try:
        # Resume the graph - keep invoking until completion or next interrupt
        max_iterations = 10
        iteration = 0
        while iteration < max_iterations:
            if is_abort_requested(req.thread_id):
                linkedin_graph.update_state(config, {
                    "approval_status": "aborted",
                    "error": "Pipeline aborted by user",
                })
                raise PipelineAborted("Pipeline aborted during approval processing")

            await asyncio.to_thread(linkedin_graph.invoke, None, config)
            state_snapshot = await asyncio.to_thread(linkedin_graph.get_state, config)
            
            # Check if we hit another interrupt or completed
            if not state_snapshot.next or state_snapshot.next == ():
                break
            
            # If we're back at human_approval interrupt, stop
            if state_snapshot.next == ("human_approval",):
                break
                
            iteration += 1
    except PipelineAborted as e:
        clear_thread_id()
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        clear_thread_id()
        raise HTTPException(status_code=500, detail=f"Approval processing failed: {e}")
    finally:
        clear_thread_id()

    # Get final state
    new_state = await asyncio.to_thread(linkedin_graph.get_state, config)
    values = new_state.values
    next_node = new_state.next

    if values.get("error"):
        error_msg = str(values.get("error"))
        approval_status = str(values.get("approval_status", "") or "")

        # Publish failures are non-fatal for approval flow; return actionable status.
        if approval_status in ("publish_failed", "approved_not_published"):
            return {
                "status": approval_status,
                "final_post": values.get("final_post", {}),
                "publish_url": values.get("publish_url", ""),
                "viral_score": values.get("viral_score", 0.0),
                "realism_score": values.get("realism_score", 0.0),
                "post_id": values.get("post_id", ""),
                "error": error_msg,
                "message": "Post approved, but publishing failed. Check LinkedIn token/author configuration and retry.",
            }
        
        # Parse low realism error to make it user-friendly
        if "rejected_due_to_low_realism" in error_msg:
            try:
                score = float(error_msg.split(":")[1])
                raise HTTPException(
                    status_code=422, 
                    detail=f"Cannot publish: Research quality score too low ({score:.2f}/1.0). The post contains claims that cannot be verified with available sources. Try regenerating or editing the topic to focus on well-documented facts."
                )
            except (IndexError, ValueError):
                raise HTTPException(
                    status_code=422,
                    detail="Cannot publish: Research quality score too low. The post contains unverifiable claims."
                )
        
        raise HTTPException(status_code=500, detail=error_msg)

    # Check if graph stopped again (regeneration → new approval needed)
    if next_node == ("human_approval",):
        return {
            "status": "awaiting_approval",
            "final_post": values.get("final_post", {}),
            "viral_score": values.get("viral_score", 0.0),
            "realism_score": values.get("realism_score", 0.0),
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
        "realism_score": values.get("realism_score", 0.0),
        "post_id": values.get("post_id", ""),
    }


@router.post("/abort")
async def abort_pipeline(req: dict):
    """
    Abort a running pipeline and clean up resources.
    This marks the thread as aborted but doesn't stop the background task.
    """
    thread_id = req.get("thread_id")
    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id required")
    
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        request_abort(thread_id)

        # Mark state as aborted
        linkedin_graph.update_state(config, {
            "approval_status": "aborted",
            "error": "Pipeline aborted by user"
        })
        
        # Disconnect any WebSocket connections for this thread
        from brain.linkedin.websocket_manager import ws_manager
        # Note: connections will be cleaned up when client disconnects
        
        return {"status": "aborted", "thread_id": thread_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Abort failed: {e}")


# ==========================================
# POST HISTORY
# ==========================================

@router.get("/posts")
async def list_posts(offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=200)):
    """List all generated LinkedIn posts."""
    posts = get_all_posts(limit=limit, offset=offset)
    return {"posts": posts, "count": len(posts), "offset": offset, "limit": limit}


@router.get("/posts/{post_id}")
async def get_post(post_id: uuid.UUID):
    """Get a specific LinkedIn post by ID."""
    post = get_post_by_id(str(post_id))
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
        "redirect_uri_note": "Ensure LINKEDIN_REDIRECT_URI points to your frontend callback: http://localhost:3000/api/linkedin/callback",
        "author_target": get_configured_author_target(),
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
    author_target = get_configured_author_target()
    if not token:
        return {
            "authenticated": False,
            "message": "No access token. Start OAuth2 flow.",
            "author_target": author_target,
        }

    authenticated = is_authenticated()
    if authenticated:
        profile = get_user_profile()
        return {
            "authenticated": True,
            "profile": {
                "name": profile.get("name", ""),
                "email": profile.get("email", ""),
            },
            "author_target": author_target,
        }

    return {
        "authenticated": False,
        "message": "Token expired or invalid. Re-authenticate.",
        "author_target": author_target,
    }


# ==========================================
# WEBSOCKET STREAMING
# ==========================================

@router.websocket("/ws/{thread_id}")
async def websocket_pipeline_status(websocket: WebSocket, thread_id: str):
    """
    WebSocket endpoint for streaming live pipeline status updates.
    
    Clients connect with a thread_id and receive real-time events as the
    LinkedIn content pipeline executes:
    - node_start: Node begins execution
    - node_complete: Node finishes (with metrics)
    - state_update: State key changes
    - error: Node fails
    - pipeline_complete: Full pipeline done
    
    Usage:
        const ws = new WebSocket('ws://127.0.0.1:8000/linkedin/ws/thread-id-123')
    """
    await ws_manager.connect(thread_id, websocket)
    
    try:
        # Send connection confirmation
        await websocket.send_json({
            "type": "connected",
            "thread_id": thread_id,
            "message": "WebSocket connected - pipeline updates will stream here"
        })
        
        # Keep connection alive and listen for messages
        # (Pipeline will broadcast via ws_manager.broadcast())
        while True:
            try:
                # Wait for messages from client (e.g., "cancel" command in future)
                data = await websocket.receive_text()
                
                # For now, just echo back (could handle "cancel" later)
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except WebSocketDisconnect:
                break
            except Exception:
                # Any other error, disconnect
                break
    
    finally:
        await ws_manager.disconnect(thread_id, websocket)


@router.get("/status/{thread_id}")
async def get_pipeline_status(thread_id: str):
    """
    Fallback HTTP endpoint to poll pipeline status if WebSocket fails.
    Returns current state snapshot from LangGraph checkpointer.
    """
    config = {"configurable": {"thread_id": thread_id}}
    
    try:
        state = linkedin_graph.get_state(config)
        
        if not state.values:
            raise HTTPException(status_code=404, detail="Thread not found")
        
        return {
            "thread_id": thread_id,
            "current_node": state.next[0] if state.next else "complete",
            "is_complete": not state.next or state.next == (),
            "viral_score": state.values.get("viral_score", 0),
            "realism_score": state.values.get("realism_score", 0),
            "iteration_count": state.values.get("iteration_count", 0),
            "approval_status": state.values.get("approval_status", ""),
            "post_id": state.values.get("post_id", ""),
            "final_post": state.values.get("final_post", {}),
            "error": state.values.get("error", ""),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Status check failed: {e}")
