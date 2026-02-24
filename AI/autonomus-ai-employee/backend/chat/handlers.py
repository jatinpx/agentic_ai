"""
Chat handlers for user interaction state machine.

Manages conversation flow: topic selection → post generation → approval → publishing.
"""

import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
import json

from chat.models import ChatState, UserAction, DailySuggestion, SuggestionTopic, UserProfile
from chat.telegram_adapter import get_telegram_adapter

logger = logging.getLogger(__name__)


class ChatStateManager:
    """Manages user chat state and conversation flow."""

    def __init__(self):
        # In-memory state storage (would use DB in production)
        self._states: Dict[str, ChatState] = {}
        self._user_profiles: Dict[str, UserProfile] = {}
        self._action_callbacks: Dict[str, Callable] = {}

    async def get_user_state(self, user_id: str) -> ChatState:
        """Get current state for user, create if doesn't exist."""
        if user_id not in self._states:
            self._states[user_id] = ChatState(
                user_id=user_id,
                platform="telegram",
            )
        return self._states[user_id]

    async def update_user_state(self, user_id: str, updates: Dict[str, Any]) -> ChatState:
        """Update user state with provided fields."""
        state = await self.get_user_state(user_id)

        for key, value in updates.items():
            if hasattr(state, key):
                setattr(state, key, value)

        self._states[user_id] = state
        return state

    async def reset_user_state(self, user_id: str):
        """Reset user state to initial."""
        self._states[user_id] = ChatState(user_id=user_id, platform="telegram")

    async def handle_callback_query(
        self,
        user_id: str,
        callback_data: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Handle Telegram callback query (button click).
        
        Args:
            user_id: User who clicked button
            callback_data: Callback data from button
            context: Additional context (chat_id, message_id, etc.)
            
        Returns:
            Dict with response data and next state
        """
        context = context or {}
        adapter = get_telegram_adapter()

        # Parse callback
        if ":" in callback_data:
            action, params = callback_data.split(":", 1)
        else:
            action = callback_data
            params = ""

        logger.info(f"User {user_id} triggered action: {action}")

        state = await self.get_user_state(user_id)

        # Route to handler based on action
        if action == "select_topic":
            return await self._handle_topic_selection(user_id, params, state, context, adapter)

        elif action == "selection_complete":
            return await self._handle_selection_complete(user_id, state, context, adapter)

        elif action == "set_format":
            return await self._handle_config_update(user_id, state, context, adapter, "post_format", params)

        elif action == "set_tone":
            return await self._handle_config_update(user_id, state, context, adapter, "post_tone", params)

        elif action == "set_goal":
            return await self._handle_config_update(user_id, state, context, adapter, "post_goal", params)

        elif action == "set_audience":
            return await self._handle_config_update(user_id, state, context, adapter, "post_audience", params)

        elif action == "set_emojis":
            return await self._handle_config_update(user_id, state, context, adapter, "include_emojis", params)

        elif action == "config_done":
            return await self._handle_config_done(user_id, state, context, adapter)

        elif action == "approve_post":
            return await self._handle_post_approval(user_id, params, state, context, adapter, approved=True)

        elif action == "reject_post":
            return await self._handle_post_approval(user_id, params, state, context, adapter, approved=False)

        elif action == "edit_post":
            return await self._handle_post_edit(user_id, params, state, context, adapter)

        else:
            logger.warning(f"Unknown callback action: {action}")
            return {"success": False, "message": "Unknown action"}

    async def _handle_topic_selection(
        self,
        user_id: str,
        topic_id: str,
        state: ChatState,
        context: Dict[str, Any],
        adapter,
    ) -> Dict[str, Any]:
        """Handle user selecting a topic."""
        # Parse "id=abc123" → "abc123" if needed
        clean_id = topic_id.split("=", 1)[-1] if "=" in topic_id else topic_id

        if clean_id not in state.selected_topic_ids:
            state.selected_topic_ids.append(clean_id)

        await self.update_user_state(user_id, {
            "selected_topic_ids": state.selected_topic_ids
        })

        # Send confirmation
        count = len(state.selected_topic_ids)
        response = {
            "success": True,
            "message": f"✅ Added topic (Total selected: {count})",
            "next_state": "waiting_for_topic_selection",
        }

        return response

    async def _handle_selection_complete(
        self,
        user_id: str,
        state: ChatState,
        context: Dict[str, Any],
        adapter,
    ) -> Dict[str, Any]:
        """Handle user completing topic selection, trigger post generation."""
        if not state.selected_topic_ids:
            return {
                "success": False,
                "message": "❌ Please select at least one topic",
            }

        # Transition to post configuration
        await self.update_user_state(user_id, {
            "state": "configuring_post",
        })

        message_id = await adapter.send_post_config_options(user_id, state, chat_id=context.get("chat_id"))
        if message_id:
            await self.update_user_state(user_id, {"config_message_id": message_id})

        return {
            "success": True,
            "message": "✅ Select post settings",
            "next_state": "configuring_post",
        }

    async def _handle_config_update(
        self,
        user_id: str,
        state: ChatState,
        context: Dict[str, Any],
        adapter,
        field: str,
        value: str,
    ) -> Dict[str, Any]:
        """Handle post configuration updates from inline buttons."""
        normalized = value.strip().lower()
        if field == "post_format" and normalized in {"short", "medium", "long"}:
            state.post_format = normalized
        elif field == "post_tone" and normalized in {"professional", "casual", "contrarian"}:
            state.post_tone = normalized
        elif field == "post_goal" and normalized in {"engagement", "authority", "leads"}:
            state.post_goal = normalized
        elif field == "post_audience":
            audience_map = {
                "tech_pros": "tech professionals",
                "eng_leaders": "engineering leaders",
                "founders": "startup founders",
            }
            state.post_audience = audience_map.get(normalized, state.post_audience)
        elif field == "include_emojis":
            if normalized in {"on", "true", "yes"}:
                state.include_emojis = True
            elif normalized in {"off", "false", "no"}:
                state.include_emojis = False

        await self.update_user_state(user_id, {
            "post_format": state.post_format,
            "post_tone": state.post_tone,
            "post_goal": state.post_goal,
            "post_audience": state.post_audience,
            "include_emojis": state.include_emojis,
        })

        chat_id = context.get("chat_id")
        if state.config_message_id and chat_id:
            await adapter.edit_post_config_options(
                chat_id=chat_id,
                message_id=state.config_message_id,
                state=state,
            )

        return {
            "success": True,
            "message": "✅ Updated post settings",
            "next_state": "configuring_post",
        }

    async def _handle_config_done(
        self,
        user_id: str,
        state: ChatState,
        context: Dict[str, Any],
        adapter,
    ) -> Dict[str, Any]:
        """Finish configuration and trigger generation."""
        if not state.selected_topic_ids:
            return {
                "success": False,
                "message": "❌ Please select at least one topic",
            }

        await self.update_user_state(user_id, {
            "state": "generating_post",
        })

        post_config = {
            "format": state.post_format,
            "tone": state.post_tone,
            "goal": state.post_goal,
            "audience": state.post_audience,
            "include_emojis": state.include_emojis,
        }

        return {
            "success": True,
            "message": "✅ Generating post...",
            "next_state": "generating_post",
            "trigger_generation": True,
            "selected_topics": state.selected_topic_ids,
            "post_config": post_config,
        }

    async def _handle_post_approval(
        self,
        user_id: str,
        post_id: str,
        state: ChatState,
        context: Dict[str, Any],
        adapter,
        approved: bool,
    ) -> Dict[str, Any]:
        """Handle user approving or rejecting generated post."""
        if approved:
            # Publication flow (in real app, call LinkedIn publishing)
            # await publish_post_to_linkedin(post_id)
            
            await self.update_user_state(user_id, {
                "state": "post_approved",
                "current_post_id": None,
            })

            response = {
                "success": True,
                "message": "✅ Post approved and published to LinkedIn!",
                "action": "publish",
                "post_id": post_id,
            }
        else:
            # Rejection flow
            await self.update_user_state(user_id, {
                "state": "post_rejected",
                "current_post_id": None,
            })

            response = {
                "success": True,
                "message": "❌ Post rejected. Would you like to try with different topics?",
                "action": "reject",
                "post_id": post_id,
            }

        return response

    async def _handle_post_edit(
        self,
        user_id: str,
        post_id: str,
        state: ChatState,
        context: Dict[str, Any],
        adapter,
    ) -> Dict[str, Any]:
        """Handle user requesting to edit post."""
        # In full implementation, this would open an editing UI
        # For now, just acknowledge

        return {
            "success": True,
            "message": "✏️ Edit mode coming soon. For now, you can reject and try again.",
            "action": "edit_prompt",
            "post_id": post_id,
        }

    async def handle_text_message(
        self,
        user_id: str,
        text: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Handle regular text message from user.
        
        Could be: editing suggestions, confirming actions, custom input, etc.
        """
        context = context or {}
        state = await self.get_user_state(user_id)

        logger.info(f"User {user_id} sent text: {text[:50]}")

        # Route based on current state
        if state.state == "awaiting_approval" and text.lower() in ("yes", "y", "approve"):
            # User texted approval for pending post
            return {
                "success": True,
                "message": "✅ Post approved",
                "action": "approve",
                "post_id": state.current_post_id,
            }

        elif state.state == "post_rejected":
            # User might be asking how to proceed
            return {
                "success": True,
                "message": "You can:\n1. Wait for tomorrow's suggestions\n2. Ask me anything about tech trends",
            }

        else:
            # Generic response
            return {
                "success": False,
                "message": "💭 I mainly work through buttons. Try using the suggestion buttons",
            }

    async def log_user_action(
        self,
        user_id: str,
        action_type: str,
        data: Dict[str, Any],
    ) -> UserAction:
        """
        Log user action for analytics/debugging.
        
        In production, save to database.
        """
        action = UserAction(
            user_id=user_id,
            action=action_type,
            data=data,
        )

        logger.info(f"Logged action for {user_id}: {action_type} -> {data}")
        return action

    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """Get user profile."""
        return self._user_profiles.get(user_id)

    async def save_user_profile(self, profile: UserProfile):
        """Save user profile."""
        self._user_profiles[profile.id] = profile
        logger.info(f"Saved profile for user {profile.id}")

    def register_action_callback(self, action: str, callback: Callable):
        """Register callback for specific action."""
        self._action_callbacks[action] = callback
        logger.info(f"Registered callback for action: {action}")

    async def invoke_action_callback(self, action: str, **kwargs) -> Any:
        """Invoke registered callback."""
        if action not in self._action_callbacks:
            logger.warning(f"No callback registered for action: {action}")
            return None

        callback = self._action_callbacks[action]
        if callable(callback):
            return await callback(**kwargs) if hasattr(callback, '__await__') else callback(**kwargs)

        return None


# Global instance
_state_manager = None


def get_chat_state_manager() -> ChatStateManager:
    """Get or create global state manager."""
    global _state_manager
    if _state_manager is None:
        _state_manager = ChatStateManager()
    return _state_manager


# Convenience functions for handling common flows

async def handle_user_callback(
    user_id: str,
    callback_data: str,
    chat_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Main entry point for handling callback queries.
    
    Usage in webhook handler:
        result = await handle_user_callback(user_id, callback_data, chat_id, message_id)
    """
    manager = get_chat_state_manager()
    context = {"chat_id": chat_id, "message_id": message_id}
    return await manager.handle_callback_query(user_id, callback_data, context)


async def handle_user_text(
    user_id: str,
    text: str,
    chat_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Handle text messages from user."""
    manager = get_chat_state_manager()
    context = {"chat_id": chat_id}
    return await manager.handle_text_message(user_id, text, context)
