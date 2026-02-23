from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class PostInput(BaseModel):
    """Pydantic model for validating LinkedIn post generation requests with full UI-configurable settings."""
    # --- Core ---
    topic: str = Field(..., description="The main topic or idea for the post")
    
    # --- Writing Style (UI overrideable) ---
    tone: str = Field(
        default="professional",
        description="Tone: professional, casual, contrarian, storytelling"
    )
    format: Optional[str] = Field(
        default=None,
        description="Post length: 'short' (80-150w), 'medium' (150-280w), 'long' (280-400w), 'article' (400-600w)"
    )
    
    # --- Content Strategy (UI overrideable) ---
    audience: str = Field(
        default="tech professionals",
        description="Target audience for the post"
    )
    goal: str = Field(
        default="engagement",
        description="Primary goal: engagement, authority, leads, awareness"
    )
    
    # --- Formatting Preferences (UI overrideable) ---
    include_emojis: bool = Field(
        default=False,
        description="Whether to include emojis in the post"
    )
    use_technical_jargon: Optional[bool] = Field(
        default=None,
        description="Use technical terminology (None = use profile default)"
    )
    cta_style: Optional[str] = Field(
        default=None,
        description="CTA style: question, provocation, invitation, actionable (None = use profile default)"
    )
    storytelling_frequency: Optional[str] = Field(
        default=None,
        description="How often to use storytelling: low, medium, high (None = use profile default)"
    )
    
    # --- Publishing (UI overrideable) ---
    auto_publish: bool = Field(
        default=False,
        description="Auto-publish to LinkedIn after approval"
    )


class PostConfigurationOptions(BaseModel):
    """Available configuration options for post generation UI."""
    tone_options: List[str] = Field(default=["professional", "casual", "contrarian", "storytelling"])
    format_options: List[Dict[str, Any]] = Field(default=[
        {"value": "short", "label": "Short (80-150 words)", "description": "Punchy, high-energy"},
        {"value": "medium", "label": "Medium (150-280 words)", "description": "Balanced narrative"},
        {"value": "long", "label": "Long (280-400 words)", "description": "Deep dive"},
        {"value": "article", "label": "Article (400-600 words)", "description": "Comprehensive guide"},
    ])
    audience_options: List[str] = Field(default=[
        "tech professionals",
        "engineering leaders",
        "product managers",
        "startup founders",
        "data scientists",
    ])
    goal_options: List[str] = Field(default=["engagement", "authority", "leads", "awareness"])
    cta_style_options: List[str] = Field(default=["question", "provocation", "invitation", "actionable"])
    storytelling_frequency_options: List[str] = Field(default=["low", "medium", "high"])


class PostGenerationRequest(BaseModel):
    """Full request for post generation with all configurable options."""
    topic: str = Field(..., description="Post topic")
    
    # Configuration overrides for this request
    tone: Optional[str] = None
    format: Optional[str] = None
    audience: Optional[str] = None
    goal: Optional[str] = None
    include_emojis: Optional[bool] = None
    use_technical_jargon: Optional[bool] = None
    cta_style: Optional[str] = None
    storytelling_frequency: Optional[str] = None
    auto_publish: Optional[bool] = None


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
