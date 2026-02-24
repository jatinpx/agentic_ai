"""
API routes for automation workflow.

Endpoints:
- POST /automation/trigger-daily: Manually trigger daily pipeline
- POST /telegram/webhook: Telegram webhook for callback queries
- GET /automation/jobs: List scheduled jobs
- POST /automation/user/profile: Update user automation settings
"""

import logging
import asyncio
import os
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from services.orchestrator import run_daily_automation, get_daily_pipeline
from services.scheduler_service import get_scheduler
from services.linkedin_api import get_auth_url, is_authenticated, get_user_profile
from db.automation_db import get_automation_db
from chat.handlers import handle_user_callback, handle_user_text
from chat.telegram_adapter import get_telegram_adapter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automation", tags=["automation"])


# ==================== Request Models ====================

class UserProfileUpdate(BaseModel):
    """Update user automation profile."""
    telegram_user_id: Optional[int] = None
    tech_interests: Optional[list[str]] = None
    automation_enabled: Optional[bool] = None
    suggestion_time: Optional[str] = None
    timezone: Optional[str] = None


class ManualTriggerRequest(BaseModel):
    """Request to manually trigger pipeline."""
    test_mode: bool = False


# ==================== Automation Routes ====================

@router.post("/trigger-daily")
async def trigger_daily_pipeline(request: ManualTriggerRequest = None) -> Dict[str, Any]:
    """
    Manually trigger the daily news-to-post automation pipeline.
    
    Used for testing and manual execution.
    """
    try:
        env_mode = os.getenv("WORKFLOW_TEST_MODE", "false").strip().lower() in ("1", "true", "yes", "on")
        use_test_mode = bool(request and request.test_mode) or env_mode
        result = await run_daily_automation(test_mode=use_test_mode)
        result["test_mode"] = use_test_mode
        return result
    except Exception as e:
        logger.error(f"Error triggering pipeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs")
async def list_scheduled_jobs() -> Dict[str, Any]:
    """List all scheduled automation jobs."""
    scheduler = get_scheduler()
    jobs = scheduler.list_jobs()
    
    return {
        "is_running": scheduler.is_running,
        "jobs_count": len(jobs),
        "jobs": jobs,
    }


@router.post("/scheduler/start")
async def start_scheduler() -> Dict[str, Any]:
    """Start the scheduler."""
    scheduler = get_scheduler()
    
    if scheduler.is_running:
        return {"success": False, "message": "Scheduler already running"}
    
    success = scheduler.start()
    
    if success:
        # Schedule daily pipeline for 8 AM UTC
        scheduler.schedule_daily_news_pipeline(
            callback=run_daily_automation,
            hour=8,
            minute=0,
            job_id="daily_news_pipeline",
        )
        
        logger.info("Scheduler started and pipeline scheduled")
        return {
            "success": True,
            "message": "Scheduler started, daily pipeline scheduled for 08:50 UTC",
        }
    else:
        return {"success": False, "message": "Failed to start scheduler"}


@router.post("/scheduler/stop")
async def stop_scheduler() -> Dict[str, Any]:
    """Stop the scheduler."""
    scheduler = get_scheduler()
    scheduler.stop()
    
    return {"success": True, "message": "Scheduler stopped"}


# ==================== User Profile Routes ====================

@router.post("/user/profile")
async def update_user_profile(user_id: str, update: UserProfileUpdate) -> Dict[str, Any]:
    """Update user's automation settings."""
    try:
        db = get_automation_db()
        
        updates = {}
        if update.tech_interests is not None:
            updates["tech_interests"] = update.tech_interests
        if update.automation_enabled is not None:
            updates["automation_enabled"] = update.automation_enabled
        if update.suggestion_time is not None:
            updates["suggestion_time"] = update.suggestion_time
        if update.timezone is not None:
            updates["timezone"] = update.timezone

        user = await db.update_user_profile(user_id, **updates)
        
        return {
            "success": True,
            "user": user,
        }
    except Exception as e:
        logger.error(f"Error updating user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user/{user_id}/profile")
async def get_user_automation_profile(user_id: str) -> Dict[str, Any]:
    """Get user's automation profile."""
    try:
        db = get_automation_db()
        # Would need a get_user method in DB service
        # For now, return placeholder
        return {"user_id": user_id, "automation_enabled": False}
    except Exception as e:
        logger.error(f"Error fetching user profile: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Telegram Webhook ====================

class TelegramWebhookBody(BaseModel):
    """Telegram webhook body."""
    update_id: int
    message: Optional[Dict[str, Any]] = None
    callback_query: Optional[Dict[str, Any]] = None


@router.post("/telegram/webhook")
async def handle_telegram_webhook(body: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle incoming Telegram webhook events.
    
    Telegram sends updates here when users:
    - Click inline buttons (callback_query)
    - Send text messages (message)
    """
    try:
        update_id = body.get("update_id")
        
        # Verify webhook secret if present
        telegram = get_telegram_adapter()
        
        # Handle callback queries (button clicks)
        if "callback_query" in body:
            callback = body["callback_query"]
            user_id = callback.get("from", {}).get("id")
            callback_data = callback.get("data")
            chat_id = callback.get("message", {}).get("chat", {}).get("id")
            message_id = callback.get("message", {}).get("message_id")
            
            if not user_id or not callback_data:
                return {"ok": False, "description": "Missing user_id or callback_data"}
            
            logger.info(f"Telegram callback: user={user_id}, action={callback_data}")

            # Resolve internal UUID
            db = get_automation_db()
            internal_user = await db.get_or_create_user(telegram_user_id=user_id)
            internal_user_id = internal_user["id"]

            # Answer callback query immediately to remove Telegram spinner
            telegram = get_telegram_adapter()
            await telegram._ensure_bot_initialized()
            callback_query_id = body.get("callback_query", {}).get("id")
            if callback_query_id and telegram.bot:
                try:
                    await telegram.bot.answer_callback_query(callback_query_id)
                except Exception:
                    pass

            # Process callback (updates in-memory state, returns signals)
            result = await handle_user_callback(
                str(user_id),
                callback_data,
                chat_id=str(chat_id),
                message_id=str(message_id),
            )

            # Act on pipeline trigger signals
            pipeline = get_daily_pipeline()

            if result.get("trigger_generation"):
                # User finished selecting topics — launch post generation
                selected_topics = result.get("selected_topics", [])
                post_config = result.get("post_config", {})
                asyncio.ensure_future(
                    pipeline.handle_user_topic_selection(
                        user_id=internal_user_id,
                        selected_topic_ids=selected_topics,
                        telegram_chat_id=str(chat_id),
                        post_config=post_config,
                    )
                )

            elif result.get("action") == "publish":
                post_id = result.get("post_id", "")
                asyncio.ensure_future(
                    pipeline.handle_post_approval(
                        user_id=internal_user_id,
                        thread_id=post_id,
                        approved=True,
                        telegram_chat_id=str(chat_id),
                    )
                )

            elif result.get("action") == "reject":
                post_id = result.get("post_id", "")
                asyncio.ensure_future(
                    pipeline.handle_post_approval(
                        user_id=internal_user_id,
                        thread_id=post_id,
                        approved=False,
                        telegram_chat_id=str(chat_id),
                    )
                )

            # Log interaction
            try:
                await db.log_chat_interaction(
                    internal_user_id,
                    "telegram_callback",
                    {"callback_data": callback_data, "result": result},
                )
            except Exception as log_err:
                logger.warning(f"Could not log interaction: {log_err}")

            return {"ok": True, "result": result}

        # Handle text messages
        elif "message" in body:
            message = body["message"]
            user_id = message.get("from", {}).get("id")
            text = message.get("text", "")
            chat_id = message.get("chat", {}).get("id")
            username = message.get("from", {}).get("username")

            if not user_id:
                return {"ok": False, "description": "Missing user_id"}

            logger.info(f"Telegram message: user={user_id}, text={text[:50]}")

            command = text.strip().lower()

            # LinkedIn auth via bot mode
            if command in ("/linkedin_auth", "/linkedin-auth", "/auth"):
                telegram = get_telegram_adapter()
                auth_url = get_auth_url()
                await telegram.send_notification(
                    user_id=str(chat_id),
                    notification_type="info",
                    message=(
                        "Connect LinkedIn to enable publishing:\n"
                        f"<a href=\"{auth_url}\">Authorize LinkedIn</a>\n\n"
                        "After authorizing, return here and send /linkedin_status"
                    ),
                    chat_id=str(chat_id),
                )
                return {"ok": True, "result": "linkedin_auth_url_sent"}

            if command in ("/linkedin_status", "/linkedin-status", "/auth_status"):
                telegram = get_telegram_adapter()
                if is_authenticated():
                    profile = get_user_profile()
                    display_name = profile.get("name") or profile.get("email") or "LinkedIn user"
                    await telegram.send_notification(
                        user_id=str(chat_id),
                        notification_type="success",
                        message=f"LinkedIn is connected as: {display_name}",
                        chat_id=str(chat_id),
                    )
                else:
                    await telegram.send_notification(
                        user_id=str(chat_id),
                        notification_type="warning",
                        message="LinkedIn is not connected yet. Send /linkedin_auth to connect.",
                        chat_id=str(chat_id),
                    )
                return {"ok": True, "result": "linkedin_status_checked"}

            # Handle /start — register user and send welcome
            if command.startswith("/start"):
                db = get_automation_db()
                try:
                    await db.get_or_create_user(
                        telegram_user_id=user_id,
                        telegram_username=username,
                    )
                except Exception as exc:
                    logger.warning(f"Could not register user {user_id}: {exc}")

                telegram = get_telegram_adapter()
                await telegram.send_notification(
                    user_id=str(chat_id),
                    notification_type="success",
                    message=(
                        "Welcome! 🤖 Your AI Content Bot is ready.\n\n"
                        "You'll receive daily LinkedIn post suggestions here. "
                        "Use the buttons to select topics and approve posts.\n\n"
                        "If publish fails, send /linkedin_auth then /linkedin_status."
                    ),
                    chat_id=str(chat_id),
                )
                return {"ok": True, "result": "registered"}

            # Process other messages
            result = await handle_user_text(str(user_id), text, chat_id=str(chat_id))

            # Log interaction with internal UUID
            try:
                db = get_automation_db()
                internal_user = await db.get_or_create_user(telegram_user_id=user_id)
                await db.log_chat_interaction(
                    internal_user["id"],
                    "telegram_message",
                    {"text": text, "result": result},
                )
            except Exception as log_err:
                logger.warning(f"Could not log interaction: {log_err}")
            
            return {"ok": True, "result": result}

        else:
            return {"ok": False, "description": "Unknown update type"}

    except Exception as e:
        logger.error(f"Error handling Telegram webhook: {e}", exc_info=True)
        return {"ok": False, "description": str(e)}


# ==================== Telegram Setup/Debug Routes ====================

@router.get("/telegram/info")
async def telegram_bot_info() -> Dict[str, Any]:
    """Get bot info and verify token is valid."""
    telegram = get_telegram_adapter()
    await telegram._ensure_bot_initialized()

    if not telegram.bot:
        return {"ok": False, "error": "Bot not initialized — check TELEGRAM_BOT_TOKEN in .env"}

    try:
        me = await telegram.bot.get_me()
        return {
            "ok": True,
            "bot_id": me.id,
            "bot_name": me.full_name,
            "bot_username": me.username,
            "hint": f"Open Telegram and send /start to @{me.username} first, then call /automation/telegram/updates",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/telegram/updates")
async def telegram_get_updates(limit: int = 10) -> Dict[str, Any]:
    """
    Poll Telegram for recent updates (messages sent to the bot).

    Use this after sending /start to the bot in Telegram to confirm
    the chat_id and verify connectivity.
    """
    telegram = get_telegram_adapter()
    await telegram._ensure_bot_initialized()

    if not telegram.bot:
        return {"ok": False, "error": "Bot not initialized"}

    try:
        updates = await telegram.bot.get_updates(limit=limit)
        parsed = []
        for u in updates:
            if u.message:
                parsed.append({
                    "update_id": u.update_id,
                    "chat_id": u.message.chat.id,
                    "user_id": u.message.from_user.id if u.message.from_user else None,
                    "username": u.message.from_user.username if u.message.from_user else None,
                    "text": u.message.text,
                    "date": str(u.message.date),
                })
        return {
            "ok": True,
            "count": len(parsed),
            "updates": parsed,
            "note": "If empty, send /start to your bot in Telegram first.",
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


class TestSendRequest(BaseModel):
    chat_id: str
    message: str = "Hello from your AI Content Bot! 🤖 Bot is configured correctly."


@router.post("/telegram/send-test")
async def telegram_send_test(body: TestSendRequest) -> Dict[str, Any]:
    """
    Send a test message to a specific Telegram chat_id.

    Steps:
      1. Open Telegram → find your bot → send /start
      2. Call GET /automation/telegram/updates to see your chat_id
      3. Call this endpoint with that chat_id to confirm sending works
    """
    telegram = get_telegram_adapter()
    ok = await telegram.send_notification(
        user_id=body.chat_id,
        notification_type="success",
        message=body.message,
        chat_id=body.chat_id,
    )
    return {"ok": ok, "chat_id": body.chat_id}


# ==================== Testing/Debug Routes ====================

@router.get("/debug/news")
async def debug_fetch_news() -> Dict[str, Any]:
    """Debug: Fetch and return news items (no ranking)."""
    try:
        from services.news_aggregator import fetch_tech_news_sync
        
        news = fetch_tech_news_sync(hours_back=24)
        
        return {
            "count": len(news),
            "items": news[:5],  # Return first 5
        }
    except Exception as e:
        logger.error(f"Error fetching news: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/topics")
async def debug_rank_topics(interests: str = "AI,Startups") -> Dict[str, Any]:
    """Debug: Rank topics from recent news."""
    try:
        from services.news_aggregator import fetch_tech_news_sync
        import asyncio
        
        news = fetch_tech_news_sync(hours_back=24)
        interests_list = [i.strip() for i in interests.split(",")]
        
        ranker = get_daily_pipeline().topic_ranker
        ranked = await ranker.rank_topics(news, interests_list, top_n=5)
        
        return {
            "count": len(ranked),
            "interests": interests_list,
            "topics": ranked,
        }
    except Exception as e:
        logger.error(f"Error ranking topics: {e}")
        raise HTTPException(status_code=500, detail=str(e))
