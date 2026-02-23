"""
User Profile Loader
Reads user_profile.yaml and provides a normalized persona dict for nodes.
Handles missing files, invalid fields, and provides safe defaults.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

# Module-level cache to avoid re-reading file on every node call
_PROFILE_CACHE: Optional[Dict[str, Any]] = None


def get_profile_path() -> Path:
    """Get path to user_profile.yaml, defaulting to backend/ directory."""
    path = Path(__file__).parent.parent / "user_profile.yaml"
    return path


def _get_safe_profile() -> Dict[str, Any]:
    """
    Load and normalize user profile from YAML.
    Returns sensible defaults if file is missing or malformed.
    """
    profile_path = get_profile_path()
    
    # Load YAML if file exists
    if profile_path.exists():
        try:
            with open(profile_path, 'r') as f:
                raw_profile = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[PROFILE LOADER] Error reading {profile_path}: {e}. Using defaults.")
            raw_profile = {}
    else:
        print(f"[PROFILE LOADER] Profile file not found at {profile_path}. Using defaults.")
        raw_profile = {}
    
    # Extract nested sections with safe fallbacks
    identity = raw_profile.get("identity", {})
    technical = raw_profile.get("technical", {})
    writing = raw_profile.get("writing", {})
    career = raw_profile.get("career", {})
    
    # Validate and normalize expertise_level
    expertise_level = technical.get("expertise_level", "intermediate").strip().lower()
    if expertise_level not in ("beginner", "intermediate", "expert"):
        expertise_level = "intermediate"
    
    # Validate and normalize default_tone
    tone = writing.get("default_tone", "professional").strip().lower()
    if tone not in ("professional", "casual", "contrarian", "storytelling"):
        tone = "professional"
    
    # Validate and normalize default_format
    default_format = writing.get("default_format", "medium").strip().lower()
    if default_format not in ("short", "medium", "long", "article"):
        default_format = "medium"
    
    # Validate and normalize cta_style
    cta_style = writing.get("cta_style", "question").strip().lower()
    if cta_style not in ("question", "provocation", "invitation", "actionable"):
        cta_style = "question"
    
    # Validate storytelling_frequency
    storytelling = writing.get("storytelling_frequency", "medium").strip().lower()
    if storytelling not in ("low", "medium", "high"):
        storytelling = "medium"
    
    # Build normalized profile
    normalized = {
        "identity": {
            "name": (identity.get("name") or "").strip() or "Author",
            "job_role": (identity.get("job_role") or "").strip() or "Tech Professional",
            "organization": (identity.get("organization") or "").strip() or "Tech Company",
            "industry": (identity.get("industry") or "").strip() or "Technology",
            "years_experience": max(0, int(identity.get("years_experience", 5) or 5)),
        },
        "technical": {
            "tech_stack": [s.strip() for s in (technical.get("tech_stack") or []) if s and isinstance(s, str)],
            "expertise_areas": [e.strip() for e in (technical.get("expertise_areas") or []) if e and isinstance(e, str)],
            "expertise_level": expertise_level,
        },
        "writing": {
            "default_tone": tone,
            "default_format": default_format,
            "emoji_preference": bool(writing.get("emoji_preference", False)),
            "cta_style": cta_style,
            "use_technical_jargon": bool(writing.get("use_technical_jargon", False)),
            "storytelling_frequency": storytelling,
        },
        "career": {
            "corporate_interest": max(0, min(10, int(career.get("corporate_interest", 5) or 5))),
            "focus_areas": [f.strip() for f in (career.get("focus_areas") or []) if f and isinstance(f, str)],
        }
    }
    
    return normalized


def load_user_profile() -> Dict[str, Any]:
    """
    Load user profile from cache or file.
    Returns normalized profile dict with all required fields populated.
    Safe to call on every node invocation (cached after first load).
    """
    global _PROFILE_CACHE
    
    if _PROFILE_CACHE is None:
        _PROFILE_CACHE = _get_safe_profile()
    
    return _PROFILE_CACHE


def reload_user_profile() -> Dict[str, Any]:
    """Force reload of profile from disk (useful for testing/reloading without restart)."""
    global _PROFILE_CACHE
    _PROFILE_CACHE = _get_safe_profile()
    return _PROFILE_CACHE


def get_profile_summary() -> str:
    """Return a human-readable summary of the loaded profile."""
    profile = load_user_profile()
    ident = profile["identity"]
    tech = profile["technical"]
    writing = profile["writing"]
    
    lines = [
        f"📋 User Profile Summary",
        f"  Role: {ident['job_role']} @ {ident['organization']} ({ident['years_experience']} yrs)",
        f"  Industry: {ident['industry']}",
        f"  Tech Stack: {', '.join(tech['tech_stack']) if tech['tech_stack'] else 'Not specified'}",
        f"  Expertise: {tech['expertise_level'].title()}",
        f"  Default Tone: {writing['default_tone'].title()}",
        f"  Default Format: {writing['default_format'].title()}",
        f"  CTA Style: {writing['cta_style'].title()}",
        f"  Storytelling: {writing['storytelling_frequency'].title()}",
    ]
    return "\n".join(lines)
