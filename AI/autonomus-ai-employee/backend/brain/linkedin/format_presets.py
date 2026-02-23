"""
Format Presets System
Defines 4 LinkedIn post formats (short/medium/long/article) with structure,
word count, and guidance for each.
"""

from typing import Dict, Tuple, Any


# ==========================================
# FORMAT PRESETS
# ==========================================
FORMAT_PRESETS: Dict[str, Dict[str, Any]] = {
    "short": {
        "display_name": "Short Post",
        "description": "Punchy, high-energy, single insight",
        "word_range": (80, 150),
        "paragraph_count": (1, 2),
        "hook_style": "single punchy sentence",
        "structure": [
            "≤1 sentence hook",
            "1-2 compact body paragraphs",
            "No lists or bullets",
            "Implicit or 1-line CTA",
        ],
        "cta_guidance": "Keep CTA implicit or very short (one line max)",
        "mobile_rule": "≤3 lines on mobile (aggressive line-breaking)",
        "depth": "beginner-friendly",
        "use_case": "Quick takes, reactions, insights for scrollers with 10 seconds attention span",
    },
    "medium": {
        "display_name": "Medium Post",
        "description": "Balanced narrative with depth and engagement",
        "word_range": (150, 280),
        "paragraph_count": (3, 5),
        "hook_style": "1-2 sentence narrative hook",
        "structure": [
            "1-2 sentence compelling hook (pattern interrupt)",
            "3-4 body paragraphs building narrative",
            "Optional 1 short bulleted list (max 3 items)",
            "1-2 sentence meaningful CTA (not generic)",
        ],
        "cta_guidance": "Open-ended question, provocation, or invitation tied to content",
        "mobile_rule": "≤3 lines per paragraph on mobile",
        "depth": "intermediate",
        "use_case": "Default LinkedIn sweet spot; works for most audiences and topics",
    },
    "long": {
        "display_name": "Long Post",
        "description": "Deeper insights with multiple examples and frameworks",
        "word_range": (280, 400),
        "paragraph_count": (5, 7),
        "hook_style": "2-3 sentence mini-narrative",
        "structure": [
            "2-3 sentence hook with context-setting",
            "5-6 body paragraphs with micro-insights",
            "Up to 2 short bulleted lists for frameworks/steps",
            "Multiple examples or case references",
            "2-3 sentence CTA with specific ask",
        ],
        "cta_guidance": "Specific invitation (e.g., 'Share your approach in comments')",
        "mobile_rule": "≤5 lines per paragraph on mobile; use blank lines to create rhythm",
        "depth": "intermediate to advanced",
        "use_case": "Deep dives, frameworks, tutorials; for engaged audiences willing to invest time",
    },
    "article": {
        "display_name": "Article Post",
        "description": "Comprehensive deep-dive with sections and structure",
        "word_range": (400, 600),
        "paragraph_count": (8, 12),
        "hook_style": "3-4 sentence problem statement or story",
        "structure": [
            "3-4 sentence hook (set up problem/opportunity)",
            "7-9 body paragraphs organized into sections (implicit or with ★/— breaks)",
            "2-3 bulleted lists for frameworks, steps, or tactics",
            "Example deep-dive or case study (1-2 paragraphs)",
            "Conclusion (1-2 paragraphs summarizing)",
            "3-4 sentence CTA with broader invitation (e.g., discussion, collaboration)",
        ],
        "cta_guidance": "Invite bigger discussion or next action (e.g., 'What would you add?')",
        "mobile_rule": "Expect lower engagement from mobile due to length; optimize readability",
        "depth": "advanced technical audience",
        "use_case": "Comprehensive guides, research findings, authoritative takes; requires patience from reader",
    },
}


def get_format_preset(format_key: str) -> Dict[str, Any]:
    """
    Get format preset by key, defaulting to 'medium' if invalid.
    
    Args:
        format_key: "short" | "medium" | "long" | "article"
    
    Returns:
        Format preset dict with all configuration
    """
    format_key = (format_key or "medium").lower().strip()
    return FORMAT_PRESETS.get(format_key, FORMAT_PRESETS["medium"])


def get_format_prompt_section(format_key: str) -> str:
    """
    Generate format-specific instructions for inclusion in LLM prompts.
    
    Returns a string describing the exact structure, length, and tone
    expected for the requested format.
    """
    preset = get_format_preset(format_key)
    
    word_min, word_max = preset["word_range"]
    para_min, para_max = preset["paragraph_count"]
    
    instructions = f"""
# FORMAT INSTRUCTIONS: {preset['display_name'].upper()}

**Target Length**: {word_min}-{word_max} words (strictly enforce this range)

**Structure**:
{chr(10).join(f"  • {s}" for s in preset['structure'])}

**Depth**: {preset['depth'].title()}
{f"  {preset['use_case']}" if preset['use_case'] else ""}

**CTA Style**: {preset['cta_guidance']}

**Mobile Constraint**: {preset['mobile_rule']}

**Key Rule**: You are writing a {format_key} post. Do NOT exceed {word_max} words.
Do NOT fall below {word_min} words. Adapt density and detail to the format."""
    
    return instructions.strip()


def validate_post_format(text: str, format_key: str, verbose: bool = False) -> Dict[str, Any]:
    """
    Validate a post against format requirements.
    
    Args:
        text: Generated post text
        format_key: "short" | "medium" | "long" | "article"
        verbose: If True, return detailed breakdown; else return pass/fail
    
    Returns:
        Dict with 'valid' (bool), 'word_count', 'paragraph_count', 'issues' (list),
        and full 'details' if verbose=True
    """
    preset = get_format_preset(format_key)
    word_min, word_max = preset["word_range"]
    
    # Count words
    word_count = len([w for w in (text or "").split() if w.strip()])
    
    # Count paragraphs (split by 2+ newlines)
    paragraphs = [p.strip() for p in (text or "").split('\n\n') if p.strip()]
    paragraph_count = len(paragraphs)
    
    # Validate
    issues = []
    if word_count < word_min:
        issues.append(f"Too short: {word_count} words (minimum {word_min})")
    elif word_count > word_max:
        issues.append(f"Too long: {word_count} words (maximum {word_max})")
    
    para_min, para_max = preset["paragraph_count"]
    if paragraph_count < para_min:
        issues.append(f"Too few paragraphs: {paragraph_count} (minimum {para_min})")
    elif paragraph_count > para_max:
        issues.append(f"Too many paragraphs: {paragraph_count} (maximum {para_max})")
    
    result = {
        "valid": len(issues) == 0,
        "format": format_key,
        "word_count": word_count,
        "paragraph_count": paragraph_count,
        "word_range": (word_min, word_max),
        "paragraph_range": (para_min, para_max),
        "issues": issues,
    }
    
    if verbose:
        result["details"] = {
            "preset": preset,
            "text_preview": text[:200] + "..." if len(text) > 200 else text,
        }
    
    return result


def get_format_list() -> list:
    """Return list of available format keys."""
    return list(FORMAT_PRESETS.keys())


def format_adjustment_for_prompt(format_key: str, current_word_count: int) -> str:
    """
    Generate a corrective prompt for the LLM if a post doesn't meet format requirements.
    
    Used by post_writer_node when validation fails.
    """
    preset = get_format_preset(format_key)
    word_min, word_max = preset["word_range"]
    
    if current_word_count < word_min:
        deficit = word_min - current_word_count
        return f"""The post is {current_word_count} words but needs at least {word_min} for a {format_key} post.
Expand by ~{deficit} words. Add:
  • More vivid examples or numbers
  • Deeper explanation of consequences
  • Additional micro-insight or story beat
  • Stronger supporting evidence"""
    
    elif current_word_count > word_max:
        excess = current_word_count - word_max
        return f"""The post is {current_word_count} words but must be ≤{word_max} for a {format_key} post.
Cut ~{excess} words while preserving the core argument. Remove:
  • Redundant explanations
  • Nice-to-have examples (keep only the strongest 1-2)
  • Overly verbose phrasing
  • Secondary arguments"""
    
    return ""
