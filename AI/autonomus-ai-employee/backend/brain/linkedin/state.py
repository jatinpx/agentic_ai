from typing import TypedDict, List


class LinkedInAgentState(TypedDict):
    """Full state for the LinkedIn content generation LangGraph pipeline."""

    # --- User Input ---
    user_input: dict          # Raw PostInput dict
    topic: str
    tone: str
    audience: str
    goal: str
    include_emojis: bool
    auto_publish: bool

    # --- Memory / Context ---
    style_examples: list      # Past user posts matching style
    viral_examples: list      # High-performing viral references
    trends: str               # Current trend research output

    # --- Hook Generation ---
    hooks: list               # List of generated hook dicts
    selected_hook: str        # Best hook selected

    # --- Post Generation ---
    generated_post: dict      # Raw generated post (PostOutput-shaped)
    optimized_post: dict      # After engagement optimization
    viral_score: float        # Final viral score 0-10

    # --- Final Output ---
    final_post: dict          # Assembled final post with all metadata
    post_id: str              # UUID from database after storage
    approval_status: str      # "awaiting", "approved", "regenerate", "rejected"
    publish_url: str          # LinkedIn post URL after publishing

    # --- Control ---
    error: str                # Error message if any node fails
    iteration_count: int      # Regeneration counter
