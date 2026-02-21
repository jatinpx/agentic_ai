from typing import TypedDict, List, Dict


class LinkedInAgentState(TypedDict):
    """Full state for the LinkedIn content generation LangGraph pipeline."""

    # --- User Input ---
    user_input: dict          # Raw PostInput dict
    topic: str
    topic_original: str
    topic_cleaned: str
    tone: str
    audience: str
    goal: str
    include_emojis: bool
    auto_publish: bool

    # --- Memory / Context ---
    style_examples: list      # Past user posts matching style (quality-gated)
    viral_examples: list      # High-performing viral references (distance-gated)
    trends: str               # Current trend research output
    trend_candidates: list    # Raw structured trend signals from web
    extracted_claims: list    # Claims extracted from raw trend signals
    verified_claims: list     # Fact-checked claims only
    counter_claims: list      # Counter-claims and controversy signals
    risk_flags: list          # Risk flags derived from contradiction search
    controversy_score: float  # Aggregate controversy signal (0-1)
    confidence_adjustment: float  # Adjustment applied after contradiction scan
    research_queries: list    # Targeted source-aware queries
    research_realism_score: float  # Realism score from verified claims only
    angle_package: dict       # Chosen strategic angle + supporting facts
    pov_package: dict          # Insider POV framing for authority tone
    research_confidence: float  # Confidence in research quality (0-1)

    # --- Hook Generation ---
    hooks: list               # List of generated hook dicts
    selected_hook: str        # Best hook selected

    # --- Post Generation ---
    generated_post: dict      # Raw generated post (PostOutput-shaped)
    optimized_post: dict      # After engagement optimization
    viral_score: float        # Final viral score 0-10
    realism_score: float      # Believability score (0-1)

    # --- Final Output ---
    final_post: dict          # Assembled final post with all metadata
    post_id: str              # UUID from database after storage
    approval_status: str      # "awaiting", "approved", "regenerate", "rejected"
    publish_url: str          # LinkedIn post URL after publishing

    # --- Control ---
    error: str                # Error message if any node fails
    iteration_count: int      # Regeneration counter
    score_feedback: dict      # Scorer feedback for next iteration improvements
    research_retry_count: int # Retry count for research confidence loop
