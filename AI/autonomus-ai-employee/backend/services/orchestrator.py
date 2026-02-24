"""
Daily Automation Pipeline Orchestrator

Coordinates: news aggregation → topic ranking → user messaging → post generation → approval → publishing

Main workflow:
1. Aggregate news from multiple sources
2. Rank topics by virality/relevance
3. Send suggestions to users via Telegram
4. Wait for user selections
5. Generate LinkedIn post via LangGraph agent
6. Send for approval
7. On approval, publish to LinkedIn
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import os

from services.news_aggregator import fetch_tech_news_sync, get_news_aggregator
from services.topic_ranker import rank_and_suggest_topics, get_topic_ranker
from services.llm_client import chat
from db.automation_db import get_automation_db
from chat.telegram_adapter import get_telegram_adapter
from chat.models import DailySuggestion, SuggestionTopic
from chat.handlers import get_chat_state_manager

logger = logging.getLogger(__name__)


class DailyPipeline:
    """Orchestrates the daily automation pipeline."""

    def __init__(self):
        self.news_agg = get_news_aggregator()
        self.topic_ranker = get_topic_ranker()
        self.db = get_automation_db()
        self.telegram = get_telegram_adapter()
        self.state_manager = get_chat_state_manager()
        self._user_test_mode: Dict[str, bool] = {}
        self._thread_test_mode: Dict[str, bool] = {}
        self._thread_test_post: Dict[str, str] = {}

    def _start_background_task(self, coro, task_name: str) -> None:
        """Create tracked background task and surface exceptions in logs."""
        task = asyncio.create_task(coro)

        def _on_done(done_task: asyncio.Task):
            try:
                done_task.result()
            except asyncio.CancelledError:
                logger.warning("Background task cancelled: %s", task_name)
            except Exception as exc:
                logger.error("Background task failed (%s): %s", task_name, exc, exc_info=True)

        task.add_done_callback(_on_done)

    async def run_daily_pipeline(self, test_mode: bool = False) -> Dict[str, Any]:
        """
        Execute the full daily pipeline.
        
        Returns status dict with execution details.
        """
        logger.info("=" * 60)
        logger.info(f"🚀 Starting daily automation pipeline (test_mode={test_mode})")
        logger.info("=" * 60)

        try:
            # Step 1: Aggregate news
            logger.info("📰 Step 1: Aggregating tech news...")
            news_items = await self.news_agg.fetch_tech_news()
            logger.info(f"✅ Aggregated {len(news_items)} news items")

            if not news_items:
                logger.warning("⚠️ No news items aggregated, aborting pipeline")
                return {
                    "success": False,
                    "message": "No news items aggregated",
                    "timestamp": datetime.now().isoformat(),
                }

            # Step 2: Get automation-enabled users
            logger.info("👥 Step 2: Fetching automation-enabled users...")
            users = await self.db.get_AutomationEnabledUsers()
            logger.info(f"✅ Found {len(users)} users with automation enabled")

            if not users:
                logger.warning("⚠️ No users with automation enabled")
                return {
                    "success": False,
                    "message": "No automation-enabled users",
                    "timestamp": datetime.now().isoformat(),
                }

            # Step 3: Rank topics and send suggestions to each user
            logger.info("📋 Step 3: Ranking topics and sending suggestions...")
            sent_count = 0
            failed_count = 0

            for user in users:
                user_id = str(user["id"])
                self._user_test_mode[user_id] = test_mode
                interests = user.get("tech_interests", ["AI", "Startups", "Tech"])

                try:
                    # Rank topics for this user
                    ranked_topics = await self.topic_ranker.rank_topics(
                        news_items,
                        user_interests=interests,
                        top_n=5,
                    )

                    if not ranked_topics:
                        logger.warning(f"⚠️ No ranked topics for user {user_id}")
                        failed_count += 1
                        continue

                    # Save suggestions to DB
                    suggestion_id = await self.db.save_daily_suggestions(
                        user_id=user_id,
                        topics=[t.dict() if hasattr(t, 'dict') else t for t in ranked_topics],
                    )

                    # Send via Telegram
                    telegram_user_id = user.get("telegram_user_id")
                    if telegram_user_id:
                        # Convert to SuggestionTopic models for adapter
                        suggestion_topics = [
                            SuggestionTopic(**t) if isinstance(t, dict) else t
                            for t in ranked_topics
                        ]

                        message_id = await self.telegram.send_topic_suggestions(
                            user_id=str(telegram_user_id),
                            topics=suggestion_topics,
                        )

                        if message_id:
                            sent_count += 1
                            logger.info(f"✅ Sent suggestions to user {telegram_user_id}")
                            await self.state_manager.update_user_state(
                                str(telegram_user_id),
                                {
                                    "state": "waiting_for_topic_selection",
                                    "selected_topic_ids": [],
                                    "post_format": "medium",
                                    "post_tone": "professional",
                                    "post_goal": "engagement",
                                    "post_audience": "tech professionals",
                                    "include_emojis": False,
                                    "config_message_id": None,
                                },
                            )
                        else:
                            logger.warning(f"⚠️ Failed to send suggestions to user {telegram_user_id}")
                            failed_count += 1
                    else:
                        logger.warning(f"⚠️ User {user_id} has no Telegram ID")
                        failed_count += 1

                except Exception as e:
                    logger.error(f"❌ Error processing user {user_id}: {e}", exc_info=True)
                    failed_count += 1

            logger.info(f"📊 Suggestions sent: {sent_count}, Failed: {failed_count}")

            return {
                "success": True,
                "message": f"Pipeline completed: {sent_count} users notified, {failed_count} failed",
                "news_items_gathered": len(news_items),
                "users_notified": sent_count,
                "users_failed": failed_count,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"❌ Pipeline failed with error: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"Pipeline failed: {str(e)}",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def handle_user_topic_selection(
        self,
        user_id: str,
        selected_topic_ids: List[str],
        telegram_chat_id: str,
        post_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Handle user completing topic selection.
        Fetches topic text, notifies user, and launches post generation in background.
        """
        try:
            logger.info(f"📍 User {user_id} selected {len(selected_topic_ids)} topics")

            # Get latest suggestions from DB
            latest_suggestions = await self.db.get_latest_suggestions(user_id)
            if not latest_suggestions:
                await self.telegram.send_notification(
                    user_id=telegram_chat_id,
                    notification_type="error",
                    message="Could not find your suggestions. Please try the pipeline again.",
                    chat_id=telegram_chat_id,
                )
                return {"success": False, "message": "No suggestions found"}

            await self.db.mark_suggestions_as_selected(str(latest_suggestions["id"]))

            # Extract topic headlines
            import json
            topics_list = latest_suggestions.get("topics", [])
            if isinstance(topics_list, str):
                topics_list = json.loads(topics_list)

            selected_ids = {str(topic_id) for topic_id in selected_topic_ids}
            selected = [t for t in topics_list if str(t.get("id")) in selected_ids]
            if not selected:
                selected = [topics_list[0]] if topics_list else []

            headlines = [t.get("headline", "") for t in selected if t.get("headline")]
            mode_from_env = os.getenv("WORKFLOW_TEST_MODE", "false").strip().lower() in ("1", "true", "yes", "on")
            workflow_test_mode = self._user_test_mode.get(user_id, False) or mode_from_env

            max_topics = 2 if workflow_test_mode else 5
            topic = " | ".join(headlines[:max_topics]) if headlines else "AI and Tech Trends"

            logger.info(f"📝 Topic for generation: {topic[:120]} (workflow_test_mode={workflow_test_mode})")

            # Notify user generation is starting
            await self.telegram.send_notification(
                user_id=telegram_chat_id,
                notification_type="pending",
                message=(
                    f"Generating your LinkedIn post about:\n"
                    f"<i>{topic[:300]}</i>\n\n"
                    + ("Workflow test mode ON: fast + low-cost draft in ~10-20s. ⚡" if workflow_test_mode else "This takes 1–2 minutes. Hang tight... ⏳")
                ),
                chat_id=telegram_chat_id,
            )

            # Launch pipeline in background (don't await — let it run async)
            self._start_background_task(
                self._run_pipeline_and_notify(
                    user_id,
                    topic,
                    telegram_chat_id,
                    workflow_test_mode,
                    post_config=post_config,
                ),
                task_name=f"pipeline_generation:{user_id}",
            )

            return {"success": True, "message": "Post generation started"}

        except Exception as e:
            logger.error(f"Error handling topic selection: {e}", exc_info=True)
            return {"success": False, "message": f"Error: {str(e)}"}

    async def _run_pipeline_and_notify(
        self,
        user_id: str,
        topic: str,
        telegram_chat_id: str,
        workflow_test_mode: bool = False,
        post_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Run LinkedIn post generation pipeline and send result via Telegram."""
        import uuid
        from brain.linkedin.routes import run_linkedin_pipeline, linkedin_graph

        thread_id = str(uuid.uuid4())
        self._thread_test_mode[thread_id] = workflow_test_mode

        config = post_config or {}
        if workflow_test_mode:
            try:
                post_text = self._generate_quick_test_post(topic, config)
                self._thread_test_post[thread_id] = post_text
                preview = f"🧪 Workflow Test Mode (cheap/fast)\n\n{post_text}"
                await self.telegram.send_post_for_approval(
                    user_id=telegram_chat_id,
                    post_content=preview,
                    post_id=thread_id,
                    chat_id=telegram_chat_id,
                )
                logger.info(f"✅ Test-mode post sent for approval (thread_id={thread_id})")
                return
            except Exception as e:
                logger.error(f"Test-mode generation error for user {user_id}: {e}", exc_info=True)
                await self.telegram.send_notification(
                    user_id=telegram_chat_id,
                    notification_type="error",
                    message=f"Workflow test mode failed: {str(e)[:200]}",
                    chat_id=telegram_chat_id,
                )
                return

        initial_state = {
            "user_input": {
                "topic": topic,
                "tone": config.get("tone", "professional"),
                "format": config.get("format", "medium"),
                "audience": config.get("audience", "tech professionals"),
                "goal": config.get("goal", "engagement"),
                "include_emojis": bool(config.get("include_emojis", False)),
                "auto_publish": False,
            },
            "topic": "", "tone": "", "audience": "", "goal": "",
            "include_emojis": False, "auto_publish": False,
            "style_examples": [], "viral_examples": [],
            "trends": "", "trend_candidates": [],
            "extracted_claims": [], "verified_claims": [],
            "angle_package": {}, "research_confidence": 0.0,
            "research_retry_count": 0, "hooks": [],
            "selected_hook": "", "generated_post": {},
            "optimized_post": {}, "viral_score": 0.0,
            "realism_score": 0.0, "final_post": {},
            "post_id": "", "approval_status": "",
            "publish_url": "", "error": "",
            "iteration_count": 0, "score_feedback": {},
            "usage_stats": {
                "llm_calls": 0, "search_calls": 0,
                "total_api_calls": 0, "prompt_tokens": 0,
                "completion_tokens": 0, "total_tokens": 0,
            },
        }

        try:
            logger.info(f"🚀 Running LinkedIn pipeline thread_id={thread_id}")
            loop = asyncio.get_event_loop()
            pipeline_timeout = int(os.getenv("LINKEDIN_PIPELINE_TIMEOUT_SEC", "240"))
            # run_linkedin_pipeline is synchronous — run in thread pool
            await asyncio.wait_for(
                loop.run_in_executor(None, run_linkedin_pipeline, thread_id, initial_state),
                timeout=pipeline_timeout,
            )

            # Get final state after pipeline pauses at human_approval
            config = {"configurable": {"thread_id": thread_id}}
            state = linkedin_graph.get_state(config)
            values = state.values

            error = values.get("error", "")
            final_post = values.get("final_post", {})
            post_text = final_post.get("post", "") if isinstance(final_post, dict) else str(final_post)
            viral_score = values.get("viral_score", 0.0)
            realism_score = values.get("realism_score", 0.0)

            if not post_text or error:
                await self.telegram.send_notification(
                    user_id=telegram_chat_id,
                    notification_type="error",
                    message=f"Post generation failed: {error or 'No content generated'}",
                    chat_id=telegram_chat_id,
                )
                return

            # Send post for Telegram approval — thread_id IS the post_id
            preview = (
                f"📊 Viral: {viral_score:.1f}/10 | Realism: {realism_score:.1f}/10\n\n"
                + post_text
            )
            approval_message_id = await self.telegram.send_post_for_approval(
                user_id=telegram_chat_id,
                post_content=preview,
                post_id=thread_id,
                chat_id=telegram_chat_id,
            )

            if not approval_message_id:
                logger.warning(
                    "Post approval message failed, sending fallback text (thread_id=%s)",
                    thread_id,
                )
                fallback_sent = await self.telegram.send_notification(
                    user_id=telegram_chat_id,
                    notification_type="warning",
                    message=(
                        "Post generated, but approval buttons failed to render. "
                        "Please use /start to refresh bot session and retry.\n\n"
                        f"Draft preview:\n{post_text[:900]}"
                    ),
                    chat_id=telegram_chat_id,
                )
                if not fallback_sent:
                    logger.error("Fallback delivery also failed for thread_id=%s", thread_id)
            else:
                logger.info(f"✅ Post sent for Telegram approval (thread_id={thread_id})")

        except asyncio.TimeoutError:
            logger.error("Pipeline timeout for user %s (thread_id=%s)", user_id, thread_id)
            try:
                await self.telegram.send_notification(
                    user_id=telegram_chat_id,
                    notification_type="error",
                    message="Post generation timed out. Please try again in a minute.",
                    chat_id=telegram_chat_id,
                )
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Pipeline error for user {user_id}: {e}", exc_info=True)
            try:
                await self.telegram.send_notification(
                    user_id=telegram_chat_id,
                    notification_type="error",
                    message=f"Post generation error: {str(e)[:300]}",
                    chat_id=telegram_chat_id,
                )
            except Exception:
                pass

    def _generate_quick_test_post(self, topic: str, post_config: Dict[str, Any]) -> str:
        """Cheap, short one-shot draft for workflow verification."""
        provider = os.getenv("LLM_PROVIDER", "ollama").strip().lower()
        default_model = "gemini-1.5-flash" if provider == "gemini" else os.getenv("OLLAMA_MODEL_DEFAULT", "qwen2.5:7b-instruct")
        configured_model = os.getenv("LINKEDIN_TEST_MODEL", default_model).strip() or default_model

        # Fallback chain for Gemini model-availability differences across keys/projects.
        if provider == "gemini":
            candidates = [
                configured_model,
                os.getenv("GEMINI_MODEL", "").strip(),
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
            ]
            models_to_try = []
            for model_name in candidates:
                if model_name and model_name not in models_to_try:
                    models_to_try.append(model_name)
        else:
            models_to_try = [configured_model]

        post_format = post_config.get("format", "short")
        tone = post_config.get("tone", "professional")
        audience = post_config.get("audience", "tech professionals")
        goal = post_config.get("goal", "engagement")
        include_emojis = bool(post_config.get("include_emojis", False))
        length_hint = {
            "short": "80-120 words",
            "medium": "150-220 words",
            "long": "260-360 words",
        }.get(post_format, "80-120 words")

        prompt = (
            "Write a LinkedIn draft to test workflow only. "
            "No heavy research, no citations, simple structure, one CTA question at end. "
            f"Target length: {length_hint}. "
            f"Tone: {tone}. Audience: {audience}. Goal: {goal}. "
            f"Emojis: {'allowed' if include_emojis else 'none'}. "
            f"Topic: {topic}"
        )
        last_error: Optional[Exception] = None
        content = ""
        for model in models_to_try:
            try:
                content = chat(
                    messages=[
                        {"role": "system", "content": "You write concise LinkedIn drafts for testing automation flows."},
                        {"role": "user", "content": prompt},
                    ],
                    model=model,
                )
                if content and content.strip():
                    logger.info(f"🧪 Workflow test mode using model: {model}")
                    break
            except Exception as exc:
                last_error = exc
                logger.warning(f"Workflow test model failed ({model}): {exc}")
                continue

        if not content or not content.strip():
            if last_error:
                raise RuntimeError(f"All workflow test models failed. Last error: {last_error}")
            return f"Testing workflow with topic: {topic}\n\nWhat are your thoughts on this trend?"
        return content.strip()

    async def handle_post_approval(
        self,
        user_id: str,
        thread_id: str,
        approved: bool,
        telegram_chat_id: str,
    ) -> Dict[str, Any]:
        """Resume the LinkedIn pipeline after user approves or rejects the post."""
        if self._thread_test_mode.get(thread_id, False):
            action = "approved" if approved else "rejected"
            if approved:
                from services.linkedin_api import publish_text_post

                test_post = self._thread_test_post.get(thread_id, "")
                if not test_post:
                    await self.telegram.send_notification(
                        user_id=telegram_chat_id,
                        notification_type="error",
                        message="🧪 Test mode: no draft found for this thread. Please run generation again.",
                        chat_id=telegram_chat_id,
                    )
                    return {"success": False, "action": action, "publish_url": ""}

                publish_result = publish_text_post(test_post)
                publish_error = publish_result.get("error")
                publish_url = publish_result.get("url", "")

                if publish_error:
                    await self.telegram.send_notification(
                        user_id=telegram_chat_id,
                        notification_type="error",
                        message=(
                            f"🧪 Test mode: publish failed: {str(publish_error)[:180]}\n"
                            "Run /linkedin_auth, complete OAuth, then check /linkedin_status and try approve again."
                        ),
                        chat_id=telegram_chat_id,
                    )
                    return {"success": False, "action": action, "publish_url": "", "error": publish_error}

                success_msg = "🧪 Test mode: published to LinkedIn successfully."
                if publish_url:
                    success_msg += f"\n{publish_url}"

                await self.telegram.send_notification(
                    user_id=telegram_chat_id,
                    notification_type="success",
                    message=success_msg,
                    chat_id=telegram_chat_id,
                )
                self._thread_test_post.pop(thread_id, None)
                self._thread_test_mode.pop(thread_id, None)
                return {"success": True, "action": action, "publish_url": publish_url}

            await self.telegram.send_notification(
                user_id=telegram_chat_id,
                notification_type="info",
                message="🧪 Test mode: rejection captured successfully.",
                chat_id=telegram_chat_id,
            )
            self._thread_test_post.pop(thread_id, None)
            self._thread_test_mode.pop(thread_id, None)
            return {"success": True, "action": action, "publish_url": ""}

        from brain.linkedin.routes import linkedin_graph

        config = {"configurable": {"thread_id": thread_id}}

        try:
            action = "approved" if approved else "rejected"
            logger.info(f"{'✅' if approved else '❌'} Post {thread_id} {action} by user {user_id}")

            linkedin_graph.update_state(config, {"approval_status": action, "error": ""})

            # Resume pipeline in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: linkedin_graph.invoke(None, config)
            )

            final_state = linkedin_graph.get_state(config)
            values = final_state.values
            publish_url = values.get("publish_url", "")
            error = values.get("error", "")

            if approved:
                if error and "publish_failed" not in values.get("approval_status", ""):
                    msg = f"Post approved but an error occurred: {error[:200]}"
                    notif_type = "warning"
                elif publish_url:
                    msg = f"🎉 Published to LinkedIn!\n{publish_url}"
                    notif_type = "success"
                else:
                    msg = "🎉 Post approved and published to LinkedIn!"
                    notif_type = "success"
            else:
                msg = "Post rejected. You'll receive new suggestions next time!"
                notif_type = "info"

            await self.telegram.send_notification(
                user_id=telegram_chat_id,
                notification_type=notif_type,
                message=msg,
                chat_id=telegram_chat_id,
            )

            return {"success": True, "action": action, "publish_url": publish_url}

        except Exception as e:
            logger.error(f"Error handling post approval: {e}", exc_info=True)
            try:
                await self.telegram.send_notification(
                    user_id=telegram_chat_id,
                    notification_type="error",
                    message=f"Approval error: {str(e)[:200]}",
                    chat_id=telegram_chat_id,
                )
            except Exception:
                pass
            return {"success": False, "message": str(e)}


# Global instance
_pipeline = None


def get_daily_pipeline() -> DailyPipeline:
    """Get or create global pipeline orchestrator."""
    global _pipeline
    if _pipeline is None:
        _pipeline = DailyPipeline()
    return _pipeline


# Entry point for scheduler
async def run_daily_automation(test_mode: Optional[bool] = None) -> Dict[str, Any]:
    """
    Main entry point called by scheduler each day.
    
    Usage in scheduler setup:
        from orchestrator import run_daily_automation
        scheduler.schedule_daily_news_pipeline(run_daily_automation, hour=8)
    """
    if test_mode is None:
        test_mode = os.getenv("WORKFLOW_TEST_MODE", "false").strip().lower() in ("1", "true", "yes", "on")
    pipeline = get_daily_pipeline()
    return await pipeline.run_daily_pipeline(test_mode=test_mode)
