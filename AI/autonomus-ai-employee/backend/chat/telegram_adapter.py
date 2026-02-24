"""
Telegram adapter for messaging integration.

Handles Telegram webhook events, message formatting, button callbacks.
Integrates with observability service for distributed tracing.
"""

import json
import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple
import hashlib
import hmac
import os

from dotenv import load_dotenv
load_dotenv()

try:
    from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton
    from telegram.constants import ChatAction
    from telegram.ext import ContextTypes
    print("✓ Telegram imports successful")
except ImportError as e:
    print(f"⚠️ Failed to import telegram: {e}")
    Bot = None
    InlineKeyboardMarkup = None
    InlineKeyboardButton = None
    ChatAction = None

from .models import DailySuggestion, SuggestionTopic, ChatState, UserAction

# Optional observability integration (graceful fallback if service not available)
try:
    from services.observability_service import get_observability_manager
    OBSERVABILITY_ENABLED = True
except ImportError:
    OBSERVABILITY_ENABLED = False
    get_observability_manager = lambda: None

logger = logging.getLogger(__name__)


def _emit_telegram_adapter_event(
    event_type: str,
    operation: Optional[str] = None,
    chat_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None,
):
    """
    Emit a structured event to the observability service for Telegram adapter operations.
    Gracefully handles case where observability is not available.
    """
    if not OBSERVABILITY_ENABLED:
        return
    
    try:
        obs = get_observability_manager()
        if not obs:
            return
        
        # Emit event for tracing
        obs._emit_event({
            "type": event_type,
            "platform": "telegram",
            "operation": operation,
            "chat_id": chat_id,
            "metadata": metadata,
            "error_message": error_message,
            "correlation_id": obs.get_correlation_id(),
        })
    except Exception:
        pass  # Observability failures should not crash the adapter


class TelegramAdapter:
    """Handles Telegram messaging and webhook callbacks."""

    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.bot = None
        self.webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "default_secret")
        self._bot_initialized = False
        self._bot_init_lock = asyncio.Lock()
        
        self._init_bot()

    def _init_bot(self):
        """Initialize Telegram bot (creates bot object, actual init is async)."""
        logger.info(f"Initializing Telegram bot... Token present: {bool(self.bot_token)}, Bot class available: {Bot is not None}")
        
        if not self.bot_token or not Bot:
            logger.warning("Telegram bot not configured")
            return

        try:
            self.bot = Bot(token=self.bot_token)
            logger.info("Telegram bot object created (will initialize on first use)")
        except Exception as e:
            logger.error(f"Failed to create Telegram bot: {e}")

    async def _ensure_bot_initialized(self):
        """Ensure bot is initialized before use (idempotent)."""
        if not self.bot or self._bot_initialized:
            return

        async with self._bot_init_lock:
            if not self.bot or self._bot_initialized:
                return

            try:
                await asyncio.wait_for(self.bot.initialize(), timeout=15)
                self._bot_initialized = True
                logger.info("Telegram bot initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Telegram bot: {e}")
                self.bot = None

    async def _send_with_retry(self, send_callable, operation: str, retries: int = 2, timeout_seconds: int = 20):
        """Run Telegram API call with timeout + retries for transient failures."""
        last_error: Optional[Exception] = None

        for attempt in range(retries + 1):
            try:
                return await asyncio.wait_for(send_callable(), timeout=timeout_seconds)
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    backoff = 0.6 * (attempt + 1)
                    logger.warning(
                        "Telegram %s failed (attempt %s/%s): %s",
                        operation,
                        attempt + 1,
                        retries + 1,
                        exc,
                    )
                    await asyncio.sleep(backoff)
                    await self._ensure_bot_initialized()
                    continue

        logger.error("Telegram %s failed after retries: %s", operation, last_error)
        
        # Emit error to observability
        _emit_telegram_adapter_event(
            event_type="telegram_error",
            operation=operation,
            error_message=str(last_error),
        )
        
        return None

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify webhook signature for security.
        
        Args:
            payload: Request body
            signature: X-Telegram-Bot-API-Secret-Chat-ID header
            
        Returns:
            True if signature is valid
        """
        expected = hmac.new(
            self.webhook_secret.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def send_topic_suggestions(
        self,
        user_id: str,
        topics: List[SuggestionTopic],
        chat_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send daily topic suggestions as Telegram message with inline buttons.
        
        Args:
            user_id: User identifier
            topics: List of ranked topics
            chat_id: Telegram chat_id (if None, user_id is used)
            
        Returns:
            Message ID if successful, None otherwise
        """
        await self._ensure_bot_initialized()
        
        if not self.bot:
            logger.error("Telegram bot not initialized")
            return None

        chat_id = chat_id or user_id

        # Emit to observability
        _emit_telegram_adapter_event(
            event_type="send_suggestions",
            chat_id=chat_id,
            metadata={"topic_count": len(topics) if topics else 0},
        )

        try:
            # Format message text
            message_text = self._format_suggestions_message(topics)

            # Create inline buttons for topic selection
            buttons = self._create_topic_buttons(topics)
            reply_markup = InlineKeyboardMarkup(buttons)

            # Send message
            message = await self.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )

            logger.info(f"Sent suggestions to user {user_id}, message_id={message.message_id}")
            return str(message.message_id)

        except Exception as e:
            logger.error(f"Error sending suggestions to user {user_id}: {e}")
            return None

    async def send_post_for_approval(
        self,
        user_id: str,
        post_content: str,
        post_id: str,
        chat_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send generated post for user approval via Telegram.
        
        Args:
            user_id: User identifier
            post_content: Full post text
            post_id: Post ID for callback
            chat_id: Telegram chat_id
            
        Returns:
            Message ID if successful
        """
        await self._ensure_bot_initialized()
        
        if not self.bot:
            logger.error("Telegram bot not initialized")
            return None

        chat_id = chat_id or user_id

        try:
            # Format post preview
            message_text = f"""
<b>✍️ Post Preview</b>

{post_content[:3500]}{"..." if len(post_content) > 3500 else ""}

<i>Approve to publish to LinkedIn?</i>
"""

            # Approval buttons
            buttons = [
                [
                    InlineKeyboardButton("✅ Approve & Publish", callback_data=f"approve_post:{post_id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"reject_post:{post_id}"),
                ],
                [
                    InlineKeyboardButton("✏️ Edit", callback_data=f"edit_post:{post_id}"),
                ],
            ]
            reply_markup = InlineKeyboardMarkup(buttons)

            message = await self._send_with_retry(
                lambda: self.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                ),
                operation="send_post_for_approval",
            )

            if not message:
                return None

            logger.info(f"Sent post for approval to user {user_id}, message_id={message.message_id}")
            return str(message.message_id)

        except Exception as e:
            logger.error(f"Error sending post to user {user_id}: {e}")
            return None

    async def send_post_config_options(
        self,
        user_id: str,
        state: ChatState,
        chat_id: Optional[str] = None,
    ) -> Optional[str]:
        """Send post configuration options before generation."""
        await self._ensure_bot_initialized()

        if not self.bot:
            logger.error("Telegram bot not initialized")
            return None

        chat_id = chat_id or user_id

        try:
            message_text = self._format_post_config_message(state)
            buttons = self._create_post_config_buttons(state)
            reply_markup = InlineKeyboardMarkup(buttons)

            message = await self.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
            return str(message.message_id)
        except Exception as e:
            logger.error(f"Error sending config options to user {user_id}: {e}")
            return None

    async def edit_post_config_options(
        self,
        chat_id: str,
        message_id: str,
        state: ChatState,
    ) -> bool:
        """Edit existing config message to reflect current selections."""
        message_text = self._format_post_config_message(state)
        buttons = self._create_post_config_buttons(state)
        reply_markup = InlineKeyboardMarkup(buttons)
        return await self.edit_message(
            chat_id=chat_id,
            message_id=message_id,
            text=message_text,
            reply_markup=reply_markup,
        )

    async def send_notification(
        self,
        user_id: str,
        notification_type: str,
        message: str,
        chat_id: Optional[str] = None,
    ) -> bool:
        """
        Send notification message to user.
        
        Args:
            user_id: User identifier
            notification_type: "success", "error", "info", etc.
            message: Message text
            chat_id: Telegram chat_id
            
        Returns:
            True if sent successfully
        """
        await self._ensure_bot_initialized()
        
        if not self.bot:
            return False

        chat_id = chat_id or user_id
        icons = {
            "success": "✅",
            "error": "❌",
            "info": "ℹ️",
            "warning": "⚠️",
            "pending": "⏳",
        }
        icon = icons.get(notification_type, "•")

        try:
            sent = await self._send_with_retry(
                lambda: self.bot.send_message(
                    chat_id=chat_id,
                    text=f"{icon} {message}",
                    parse_mode="HTML",
                ),
                operation="send_notification",
            )
            return bool(sent)
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")
            return False

    async def edit_message(
        self,
        chat_id: str,
        message_id: str,
        text: str,
        reply_markup: Optional[Any] = None,
    ) -> bool:
        """Edit existing message."""
        await self._ensure_bot_initialized()
        
        if not self.bot:
            return False

        try:
            edited = await self._send_with_retry(
                lambda: self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=int(message_id),
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode="HTML",
                ),
                operation="edit_message",
                retries=1,
            )
            return bool(edited)
        except Exception as e:
            logger.error(f"Error editing message {message_id}: {e}")
            return False

    async def delete_message(self, chat_id: str, message_id: str) -> bool:
        """Delete a message."""
        await self._ensure_bot_initialized()
        
        if not self.bot:
            return False

        try:
            deleted = await self._send_with_retry(
                lambda: self.bot.delete_message(chat_id=chat_id, message_id=int(message_id)),
                operation="delete_message",
                retries=1,
            )
            return bool(deleted)
        except Exception as e:
            logger.error(f"Error deleting message {message_id}: {e}")
            return False

    async def send_typing_indicator(self, chat_id: str):
        """Send typing indicator (shown as "..." in Telegram)."""
        await self._ensure_bot_initialized()
        
        if not self.bot or not ChatAction:
            return

        try:
            await self.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        except Exception as e:
            logger.warning(f"Error sending typing indicator: {e}")

    def parse_callback_query(self, callback_data: str) -> Tuple[str, Dict[str, str]]:
        """
        Parse callback query data.
        
        Format: "action:param1=value1,param2=value2"
        Examples:
            "select_topic:id=abc123"
            "approve_post:id=post123"
            
        Returns:
            Tuple of (action, params_dict)
        """
        if ":" not in callback_data:
            return callback_data, {}

        action, params_str = callback_data.split(":", 1)
        params = {}

        for param in params_str.split(","):
            if "=" in param:
                key, value = param.split("=", 1)
                params[key.strip()] = value.strip()

        return action, params

    def _format_suggestions_message(self, topics: List[SuggestionTopic]) -> str:
        """Format topic suggestions as readable message."""
        lines = ["<b>📰 Today's Tech Topics</b>", ""]

        for idx, topic in enumerate(topics, 1):
            lines.append(f"<b>{idx}. {topic.headline}</b>")
            lines.append(f"   Score: {topic.score}/100 | Category: {topic.category}")
            if topic.content_angles:
                lines.append(f"   Angles: {', '.join(topic.content_angles[:2])}")
            lines.append(f"   Source: {topic.source}")
            lines.append("")

        lines.append("<i>Select topics to generate a post</i>")
        return "\n".join(lines)

    def _create_topic_buttons(self, topics: List[SuggestionTopic]) -> List[List[Any]]:
        """Create inline buttons for topic selection."""
        buttons = []

        # Create a row for each topic
        for topic in topics:
            button_text = f"#{topic.rank} {topic.headline[:30]}..."
            callback_data = f"select_topic:id={topic.id}"
            
            buttons.append([
                InlineKeyboardButton(button_text, callback_data=callback_data)
            ])

        # Add "Multi-select done" button at end
        buttons.append([
            InlineKeyboardButton("✅ Done Selecting", callback_data="selection_complete")
        ])

        return buttons

    def _format_post_config_message(self, state: ChatState) -> str:
        """Format post configuration summary."""
        lines = ["<b>⚙️ Post Settings</b>", ""]
        lines.append(f"Size: <b>{state.post_format}</b>")
        lines.append(f"Tone: <b>{state.post_tone}</b>")
        lines.append(f"Goal: <b>{state.post_goal}</b>")
        lines.append(f"Audience: <b>{state.post_audience}</b>")
        lines.append(f"Emojis: <b>{'on' if state.include_emojis else 'off'}</b>")
        lines.append("")
        lines.append("<i>Select options or tap Done to generate.</i>")
        return "\n".join(lines)

    def _create_post_config_buttons(self, state: ChatState) -> List[List[Any]]:
        """Create inline buttons for post configuration."""
        def mark(label: str, active: bool) -> str:
            return f"✅ {label}" if active else label

        buttons = [
            [
                InlineKeyboardButton(
                    mark("Short", state.post_format == "short"),
                    callback_data="set_format:short",
                ),
                InlineKeyboardButton(
                    mark("Medium", state.post_format == "medium"),
                    callback_data="set_format:medium",
                ),
                InlineKeyboardButton(
                    mark("Long", state.post_format == "long"),
                    callback_data="set_format:long",
                ),
            ],
            [
                InlineKeyboardButton(
                    mark("Professional", state.post_tone == "professional"),
                    callback_data="set_tone:professional",
                ),
                InlineKeyboardButton(
                    mark("Casual", state.post_tone == "casual"),
                    callback_data="set_tone:casual",
                ),
                InlineKeyboardButton(
                    mark("Contrarian", state.post_tone == "contrarian"),
                    callback_data="set_tone:contrarian",
                ),
            ],
            [
                InlineKeyboardButton(
                    mark("Engagement", state.post_goal == "engagement"),
                    callback_data="set_goal:engagement",
                ),
                InlineKeyboardButton(
                    mark("Authority", state.post_goal == "authority"),
                    callback_data="set_goal:authority",
                ),
                InlineKeyboardButton(
                    mark("Leads", state.post_goal == "leads"),
                    callback_data="set_goal:leads",
                ),
            ],
            [
                InlineKeyboardButton(
                    mark("Tech Pros", state.post_audience == "tech professionals"),
                    callback_data="set_audience:tech_pros",
                ),
                InlineKeyboardButton(
                    mark("Eng Leaders", state.post_audience == "engineering leaders"),
                    callback_data="set_audience:eng_leaders",
                ),
                InlineKeyboardButton(
                    mark("Founders", state.post_audience == "startup founders"),
                    callback_data="set_audience:founders",
                ),
            ],
            [
                InlineKeyboardButton(
                    mark("Emojis On", state.include_emojis is True),
                    callback_data="set_emojis:on",
                ),
                InlineKeyboardButton(
                    mark("Emojis Off", state.include_emojis is False),
                    callback_data="set_emojis:off",
                ),
            ],
            [InlineKeyboardButton("✅ Done", callback_data="config_done")],
        ]

        return buttons


# Global instance
_telegram_adapter = None


def get_telegram_adapter() -> TelegramAdapter:
    """Get or create global Telegram adapter."""
    global _telegram_adapter
    if _telegram_adapter is None:
        _telegram_adapter = TelegramAdapter()
    return _telegram_adapter


async def send_suggestions_to_user(
    user_id: str,
    topics: List[SuggestionTopic],
) -> Optional[str]:
    """
    Convenience function to send suggestions.
    
    Usage:
        from chat.telegram_adapter import send_suggestions_to_user
        await send_suggestions_to_user("123456789", ranked_topics)
    """
    adapter = get_telegram_adapter()
    return await adapter.send_topic_suggestions(user_id, topics)


async def send_post_to_user(
    user_id: str,
    post_content: str,
    post_id: str,
) -> Optional[str]:
    """Convenience function to send post for approval."""
    adapter = get_telegram_adapter()
    return await adapter.send_post_for_approval(user_id, post_content, post_id)
