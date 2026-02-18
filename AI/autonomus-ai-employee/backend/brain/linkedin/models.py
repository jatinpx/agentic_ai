from pydantic import BaseModel, Field
from typing import List, Optional


class PostInput(BaseModel):
    """Pydantic model for validating LinkedIn post generation requests."""
    topic: str = Field(..., description="The main topic or idea for the post")
    tone: str = Field(
        default="professional",
        description="Tone of the post: professional, casual, contrarian, storytelling"
    )
    audience: str = Field(
        default="tech professionals",
        description="Target audience for the post"
    )
    goal: str = Field(
        default="engagement",
        description="Primary goal: engagement, authority, leads, awareness"
    )
    include_emojis: bool = Field(
        default=False,
        description="Whether to include emojis in the post"
    )
    auto_publish: bool = Field(
        default=False,
        description="Auto-publish to LinkedIn after approval"
    )


class PostOutput(BaseModel):
    """Structured output from the post generation pipeline."""
    hook: str = Field(..., description="Opening hook line(s)")
    post: str = Field(..., description="Full post body")
    cta: str = Field(..., description="Call-to-action ending")
    hashtags: List[str] = Field(default_factory=list, description="Relevant hashtags")
    viral_score_prediction: float = Field(
        default=0.0, ge=0, le=10,
        description="Predicted viral score 0-10"
    )
    reasoning: str = Field(
        default="",
        description="Why this post will perform well"
    )


class LinkedInApprovalRequest(BaseModel):
    """Request model for approving/rejecting a generated post."""
    thread_id: str
    action: str = Field(
        ...,
        description="Action to take: 'approved', 'regenerate', 'rejected'"
    )
    edited_post: Optional[str] = Field(
        default=None,
        description="Optional edited post text if user wants manual edits"
    )


class LinkedInAuthCallback(BaseModel):
    """OAuth2 callback parameters."""
    code: str
    state: Optional[str] = None
