"""
LinkedIn Post Configuration Service
Provides UI-configurable options and merges user selections with profile defaults.
"""

from typing import Dict, Any, Optional
from brain.linkedin.models import PostConfigurationOptions, PostGenerationRequest, PostInput
from utilities.profile_loader import load_user_profile


def get_configuration_options() -> Dict[str, Any]:
    """
    Get all available configuration options for the UI.
    Returns what choices are available for each setting.
    """
    profile = load_user_profile()
    
    options = PostConfigurationOptions()
    
    industry_raw = profile["identity"]["industry"]
    industries = [s.strip() for s in industry_raw.split(",") if s.strip()] if industry_raw else []
    if not industries and industry_raw:
        industries = [industry_raw]

    return {
        "tone_options": options.tone_options,
        "format_options": options.format_options,
        "audience_options": options.audience_options,
        "goal_options": options.goal_options,
        "cta_style_options": options.cta_style_options,
        "storytelling_frequency_options": options.storytelling_frequency_options,
        "current_defaults": {
            "tone": profile["writing"]["default_tone"],
            "format": profile["writing"]["default_format"],
            "audience": "tech professionals",  # Default audience (not in profile)
            "goal": "engagement",  # Default goal (not in profile)
            "include_emojis": profile["writing"]["emoji_preference"],
            "use_technical_jargon": profile["writing"]["use_technical_jargon"],
            "cta_style": profile["writing"]["cta_style"],
            "storytelling_frequency": profile["writing"]["storytelling_frequency"],
            "auto_publish": False,
        },
        "user_profile": {
            "name": profile["identity"]["name"],
            "role": profile["identity"]["job_role"],
            "organization": profile["identity"]["organization"],
            "industries": industries,
            "experience_years": profile["identity"]["years_experience"],
            "tech_stack": profile["technical"]["tech_stack"],
        }
    }


def merge_request_with_profile(request: PostGenerationRequest) -> PostInput:
    """
    Merge user request settings with profile defaults.
    Request overrides > Profile defaults.
    Returns a full PostInput ready for the pipeline.
    """
    profile = load_user_profile()
    
    # Resolve each field: request override > profile default > system default
    tone = (request.tone or "").strip().lower()
    if not tone:
        tone = profile["writing"]["default_tone"]
    
    format_val = (request.format or "").strip().lower()
    if not format_val:
        format_val = profile["writing"]["default_format"]
    
    audience = (request.audience or "").strip()
    if not audience:
        audience = "tech professionals"
    
    goal = (request.goal or "").strip().lower()
    if not goal:
        goal = "engagement"
    
    include_emojis = request.include_emojis
    if include_emojis is None:
        include_emojis = profile["writing"]["emoji_preference"]
    
    use_jargon = request.use_technical_jargon
    if use_jargon is None:
        use_jargon = profile["writing"]["use_technical_jargon"]
    
    cta_style = (request.cta_style or "").strip().lower()
    if not cta_style:
        cta_style = profile["writing"]["cta_style"]
    
    storytelling = (request.storytelling_frequency or "").strip().lower()
    if not storytelling:
        storytelling = profile["writing"]["storytelling_frequency"]
    
    auto_pub = request.auto_publish
    if auto_pub is None:
        auto_pub = False
    
    # Build PostInput with all resolved values
    return PostInput(
        topic=request.topic,
        tone=tone,
        format=format_val,
        audience=audience,
        goal=goal,
        include_emojis=include_emojis,
        use_technical_jargon=use_jargon,
        cta_style=cta_style,
        storytelling_frequency=storytelling,
        auto_publish=auto_pub,
    )


def get_profile_summary() -> Dict[str, Any]:
    """Get current user profile summary for display in UI."""
    profile = load_user_profile()
    industry_raw = profile["identity"]["industry"]
    industries = [s.strip() for s in industry_raw.split(",") if s.strip()] if industry_raw else []
    if not industries and industry_raw:
        industries = [industry_raw]
    
    return {
        "name": profile["identity"]["name"],
        "role": profile["identity"]["job_role"],
        "organization": profile["identity"]["organization"],
        "industries": industries,
        "experience_years": profile["identity"]["years_experience"],
        "tech_stack": profile["technical"]["tech_stack"],
        "identity": {
            "name": profile["identity"]["name"],
            "job_role": profile["identity"]["job_role"],
            "organization": profile["identity"]["organization"],
            "industry": profile["identity"]["industry"],
            "years_experience": profile["identity"]["years_experience"],
        },
        "technical": {
            "tech_stack": profile["technical"]["tech_stack"],
            "expertise_areas": profile["technical"]["expertise_areas"],
            "expertise_level": profile["technical"]["expertise_level"],
        },
        "writing": {
            "default_tone": profile["writing"]["default_tone"],
            "default_format": profile["writing"]["default_format"],
            "emoji_preference": profile["writing"]["emoji_preference"],
            "cta_style": profile["writing"]["cta_style"],
            "use_technical_jargon": profile["writing"]["use_technical_jargon"],
            "storytelling_frequency": profile["writing"]["storytelling_frequency"],
        },
        "career": {
            "corporate_interest": profile["career"]["corporate_interest"],
            "focus_areas": profile["career"]["focus_areas"],
        }
    }
