"""
Chat data models for messaging integrations.
"""

from typing import List, Optional, Literal, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class ChatMessage(BaseModel):
    """Chat message model."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    platform: Literal["telegram", "whatsapp", "discord"] = "telegram"
    user_id: str  # User identifier on platform (e.g., Telegram user_id)
    chat_id: str  # Group/channel identifier
    text: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    message_type: Literal["text", "button", "inline_button"] = "text"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SuggestionTopic(BaseModel):
    """Topic suggestion from news aggregation pipeline."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    headline: str
    source: str
    url: str
    category: str
    score: float = Field(ge=0, le=100)
    virality_score: float = Field(ge=0, le=100)
    relevance_score: float = Field(ge=0, le=100)
    content_angles: List[str]
    rank: int


class DailySuggestion(BaseModel):
    """Daily suggestion set sent to user."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    topics: List[SuggestionTopic]
    sent_at: datetime = Field(default_factory=datetime.utcnow)
    message_id: str  # Platform-specific message ID (for editing/reactions)
    status: Literal["sent", "selected", "archived"] = "sent"  # seleced = user picked topics


class UserAction(BaseModel):
    """User action on suggestion (selection, approval, rejection)."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    action: Literal["select_topic", "approve_post", "reject_post", "edit_post"] = "select_topic"
    data: Dict[str, Any]  # Action-specific data
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    platform: Literal["telegram", "whatsapp"] = "telegram"


class UserProfile(BaseModel):
    """Extended user profile for automations."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    telegram_user_id: Optional[str] = None  # Telegram user_id for messaging
    telegram_username: Optional[str] = None
    whatsapp_phone: Optional[str] = None  # WhatsApp phone + country code
    tech_interests: List[str] = Field(default_factory=list)  # ["AI", "Startups", etc]
    automation_enabled: bool = False  # Opt-in to daily suggestions
    suggestion_time: str = "08:00"  # UTC time (HH:MM format)
    timezone: str = "UTC"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChatState(BaseModel):
    """State machine for chat interaction flow."""
    user_id: str
    platform: Literal["telegram", "whatsapp"] = "telegram"
    state: Literal[
        "waiting_for_topic_selection",
        "configuring_post",
        "generating_post",
        "awaiting_approval",
        "post_approved",
        "post_rejected",
    ] = "waiting_for_topic_selection"
    current_suggestions: Optional[DailySuggestion] = None
    selected_topic_ids: List[str] = Field(default_factory=list)  # Topics user selected
    post_format: str = "medium"
    post_tone: str = "professional"
    post_audience: str = "tech professionals"
    post_goal: str = "engagement"
    include_emojis: bool = False
    config_message_id: Optional[str] = None
    current_post_id: Optional[str] = None  # Generated post awaiting approval
    current_post_content: Optional[str] = None  # Full post text
    last_message_id: Optional[str] = None  # Last message in conversation
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None  # Allow session timeout
