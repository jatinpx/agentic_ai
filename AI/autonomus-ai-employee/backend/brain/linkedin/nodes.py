"""
LinkedIn Content Agent — 11 LangGraph Node Functions.

Each node:
  - Reads its model from an env var (LINKEDIN_MODEL_*)
  - Uses services.llm_client.chat() for LLM calls
  - Uses structured logging via logging_utils
  - Returns a partial state dict (only keys it modifies)
"""

import os
import re
import json
import ast
import time
import math
from typing import Dict, Any
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

from services.llm_client import chat
from services.memory_service import recall_memory
from services.memory_picker import pick_memory_for_role
from embeddings.embedder import embed_text
from tools.tavily_web_search import tavily_search, tavily_search_structured
from brain.linkedin.usage_tracker import track_llm_call, track_search_call, get_usage_tracker
from brain.linkedin.format_presets import FORMAT_PRESETS, get_format_preset, get_format_prompt_section
from utilities.profile_loader import load_user_profile
from db.linkedin_repo import (
    insert_post,
    search_similar_posts,
    search_viral_templates,
    get_top_posts,
    update_post_status,
    insert_research_snapshot,
    insert_angle_result,
    insert_post_engagement,
)
from services.linkedin_api import publish_text_post, get_access_token, fetch_post_engagement
from brain.linkedin.models import PostInput
from brain.linkedin.logging_utils import (
    log_node, log_agent_start, log_agent_end,
    log_state_update, log_token_usage, log_error, NodeTimer,
)


# ==========================================
# PER-NODE MODEL CONFIGURATION (provider-aware)
# ==========================================
# Supports switching between Ollama and Gemini via LLM_PROVIDER env var.
# Each node reads from LINKEDIN_MODEL_* (Ollama) or LINKEDIN_GEMINI_MODEL_* (Gemini).
#
# When LLM_PROVIDER=ollama → uses LINKEDIN_MODEL_WRITER etc.
# When LLM_PROVIDER=gemini → uses LINKEDIN_GEMINI_MODEL_WRITER etc.
#
# The chat() function in llm_client.py routes to the correct backend,
# but we need provider-correct model names (e.g. "qwen2.5:7b-instruct"
# for Ollama vs "gemini-2.0-flash" for Gemini).
# ==========================================

OLLAMA_DEFAULT = "qwen2.5:7b-instruct"
GEMINI_DEFAULT = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def _get_provider() -> str:
    """Get current LLM provider (ollama or gemini)."""
    return os.getenv("LLM_PROVIDER", "ollama").strip().lower()


def _is_workflow_test_mode() -> bool:
    """Workflow-only mode: prioritize speed/cost over quality for end-to-end testing."""
    return os.getenv("WORKFLOW_TEST_MODE", "false").strip().lower() in ("1", "true", "yes", "on")


def _is_low_cost_mode() -> bool:
    """Reduce paid/free-tier API pressure by skipping non-essential LLM calls."""
    explicit_low_cost = os.getenv("LINKEDIN_LOW_COST_MODE", "false").strip().lower() in ("1", "true", "yes", "on")
    return explicit_low_cost or _is_workflow_test_mode()


def _get_model(node_key: str) -> str:
    """
    Get the model name for a specific node, respecting the active LLM provider.

    Lookup order:
      Ollama: LINKEDIN_MODEL_{node_key} → OLLAMA_MODEL_DEFAULT → hardcoded fallback
      Gemini: LINKEDIN_GEMINI_MODEL_{node_key} → GEMINI_MODEL → hardcoded fallback
    """
    provider = _get_provider()

    # Workflow test mode: force cheapest model for all nodes.
    if _is_workflow_test_mode():
        override = os.getenv("LINKEDIN_TEST_MODEL", "").strip()
        if override:
            return override
        return "gemini-1.5-flash" if provider == "gemini" else os.getenv("OLLAMA_MODEL_DEFAULT", OLLAMA_DEFAULT)

    if provider == "gemini":
        # Check per-node Gemini model first, then global GEMINI_MODEL
        model = os.getenv(f"LINKEDIN_GEMINI_MODEL_{node_key}")
        if model:
            return model
        return os.getenv("GEMINI_MODEL", GEMINI_DEFAULT)
    else:
        # Check per-node Ollama model first, then global OLLAMA_MODEL_DEFAULT
        model = os.getenv(f"LINKEDIN_MODEL_{node_key}")
        if model:
            return model
        return os.getenv("OLLAMA_MODEL_DEFAULT", OLLAMA_DEFAULT)


# Per-node model getters (lazy — read env at call time, not import time)
MODEL_INPUT       = lambda: _get_model("INPUT")
MODEL_STYLE_FETCH = lambda: _get_model("STYLE_FETCH")
MODEL_VIRAL_FETCH = lambda: _get_model("VIRAL_FETCH")
MODEL_TREND       = lambda: _get_model("TREND")
MODEL_TREND_DISCOVERY = lambda: _get_model("TREND_DISCOVERY")
MODEL_QUERY_REFINE = lambda: _get_model("QUERY_REFINE")
MODEL_QUERY_GEN = lambda: _get_model("QUERY_GEN")
MODEL_CLAIM_EXTRACT = lambda: _get_model("CLAIM_EXTRACT")
MODEL_FACT_VERIFY = lambda: _get_model("FACT_VERIFY")
MODEL_ANGLE = lambda: _get_model("ANGLE")
MODEL_POV = lambda: _get_model("POV")
MODEL_HOOK_GEN    = lambda: _get_model("HOOK_GEN")
MODEL_WRITER      = lambda: _get_model("WRITER")
MODEL_OPTIMIZER   = lambda: _get_model("OPTIMIZER")
MODEL_SCORER      = lambda: _get_model("SCORER")


# ==========================================
# EMBEDDING QUALITY THRESHOLDS
# ==========================================
# Cosine distance caps — lower = stricter match (0 = identical, 1 = opposite)
def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


STYLE_MAX_DISTANCE = _env_float("STYLE_MAX_DISTANCE", 0.35)     # Only very close style matches
VIRAL_MAX_DISTANCE = _env_float("VIRAL_MAX_DISTANCE", 0.40)     # Slightly looser for viral templates
SIMILAR_MAX_DISTANCE = _env_float("SIMILAR_MAX_DISTANCE", 0.45) # For scorer comparison
MEMORY_MAX_DISTANCE = _env_float("MEMORY_MAX_DISTANCE", 0.40)   # For general memory recall
MIN_STORE_SCORE = 5.0         # Don't store posts scoring below this
MIN_RETRIEVAL_SCORE = 5.0     # Don't retrieve low-quality past posts

# ==========================================
# MASTER SYSTEM PROMPT
# ==========================================
MASTER_PROMPT = """You are a world-class LinkedIn ghostwriter used by top founders, VCs, and tech leaders.

YOUR WRITING PRINCIPLES:
1. PATTERN INTERRUPT: The first line must break the reader's scroll reflex. Use unexpected statements, bold claims, or counterintuitive openings.
2. INFORMATION DENSITY: Every sentence must teach, provoke, or move the story forward. Zero filler.
3. VOICE AUTHENTICITY: Write with authoritative insight from the writer's real experience — not a chatbot summarizing the internet. Sound credible, specific, and grounded. Name real tools, numbers, and methodologies. Anonymize company-specific details (e.g., turn "At CompanyX" into "When teams", "For instance" examples).
4. STRUCTURAL RHYTHM: Alternate between 1-line punches and 2-3 line explanations. Use whitespace aggressively. One idea per paragraph.
5. EMOTIONAL ARC: Every post needs tension → insight → resolution. The reader should feel something shift in their understanding.
6. ENGAGEMENT ENGINEERING: End with a genuine question that people WANT to answer — not a generic "What do you think?" but a specific dilemma or choice.

HARD RULES:
- NEVER use these words/phrases: "In today's fast-paced world", "game-changer", "let's dive in", "Here's the thing", "It's not about X, it's about Y" (unless given as user style)
- NEVER start with a question (questions are weak hooks on LinkedIn)
- NEVER use more than 3 hashtags
- NEVER write paragraphs longer than 3 lines
- NEVER use bullet points in the first half of the post — earn the reader's attention with narrative first
- If the user says no emojis → absolute zero emojis, not even in hashtags
- NEVER mention your company name or specific employer in success stories — frame as industry patterns or anonymized case studies
- Keep total post length between 150-280 words (LinkedIn sweet spot for engagement)

QUALITY BAR:
- Would a VP of Engineering at a FAANG company share this? If not, rewrite.
- Does every line pass the "so what?" test? If a line doesn't change the reader's action or belief, cut it.
- Is the authority earned through insight, not through name-dropping your company?
- Could this resonate with leaders in this industry sector broadly, not just within one company?
"""


def _clean_think_tags(text: str) -> str:
    """Remove <think>...</think> tags from LLM output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _parse_json_from_llm(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    cleaned = _clean_think_tags(text)
    cleaned = cleaned.strip()

    # Collect parse candidates from code blocks and bracket spans
    candidates = [cleaned]

    code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned, flags=re.IGNORECASE)
    candidates.extend(cb.strip() for cb in code_blocks if cb.strip())

    first_brace, last_brace = cleaned.find("{"), cleaned.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        candidates.append(cleaned[first_brace:last_brace + 1].strip())

    first_bracket, last_bracket = cleaned.find("["), cleaned.rfind("]")
    if first_bracket != -1 and last_bracket > first_bracket:
        candidates.append(cleaned[first_bracket:last_bracket + 1].strip())

    for candidate in candidates:
        if not candidate:
            continue
        # Strict JSON first
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
        except Exception:
            pass

        # Python literal fallback (helps local LLM outputs with single quotes)
        try:
            parsed = ast.literal_eval(candidate)
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"items": parsed}
        except Exception:
            pass

    return {}


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text or ""))


def _is_generic_cta(cta: str) -> bool:
    low = (cta or "").strip().lower()
    generic_patterns = [
        "what do you think",
        "thoughts",
        "drop your thoughts",
        "let me know",
        "comment below",
        "your take",
    ]
    return any(p in low for p in generic_patterns)


def _extract_hook_candidates(raw_text: str, topic: str) -> list:
    """Best-effort extraction of hook lines from messy local-LLM output."""
    cleaned = _clean_think_tags(raw_text)
    lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]

    hooks = []
    disallowed_prefixes = (
        "here are",
        "the best hook",
        "this hook works",
        "reason",
        "output",
        "json",
        "hook types",
        "task",
    )
    for ln in lines:
        ln = re.sub(r"^[\-\*\d\.)\s]+", "", ln).strip().strip('"')
        if len(ln) < 18 or len(ln) > 180:
            continue
        ll = ln.lower()
        if ll.startswith(disallowed_prefixes):
            continue
        if any(token in ll for token in ["{", "}", "\"text\"", "best_hook_index", "strength_score"]):
            continue
        if ll.startswith(("type", "reason", "best_hook", "hook:")):
            ln = ln.split(":", 1)[-1].strip()
        if len(ln.split()) < 5:
            continue
        hooks.append(ln)

    # Deduplicate while preserving order
    deduped = []
    seen = set()
    for hook in hooks:
        key = re.sub(r"\W+", "", hook.lower())
        if key and key not in seen:
            seen.add(key)
            deduped.append(hook)

    # Last-resort hook bank to avoid single-hook output
    if len(deduped) < 5:
        fallback_bank = [
            f"Most teams misunderstand {topic} — and it is costing them months.",
            f"After watching smart teams fail with {topic}, one pattern keeps repeating.",
            f"Unpopular take: most advice about {topic} is optimized for likes, not results.",
            f"I used to think {topic} was about tools. It is actually about decision quality.",
            f"If your strategy for {topic} fits in one sentence, it is probably too shallow.",
        ]
        for item in fallback_bank:
            key = re.sub(r"\W+", "", item.lower())
            if key not in seen:
                seen.add(key)
                deduped.append(item)
            if len(deduped) >= 5:
                break

    return deduped[:5]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _source_quality_from_url(url: str) -> float:
    if not url:
        return 0.3
    u = url.lower()
    high = ["reuters.com", "bloomberg.com", "ft.com", "economictimes", "moneycontrol", "forbes", "techcrunch", "thehindu", "livemint"]
    medium = ["github.com", "arxiv.org", "analyticsvidhya", "towardsdatascience"]
    open_platforms = ["medium.com", "substack", "hashnode", "dev.to", "wordpress"]
    if any(h in u for h in high):
        return 0.9
    if any(m in u for m in medium):
        return 0.75
    if any(o in u for o in open_platforms):
        return 0.45
    return 0.5


def _weighted_source_quality(source_quality_avg: float, source_count: int) -> float:
    weighted = _safe_float(source_quality_avg, 0.0) * math.log(max(int(source_count), 0) + 1)
    return _clamp(weighted, 0.0, 1.0)


def _independence_score(unique_domains: int) -> float:
    if unique_domains >= 3:
        return 1.0
    if unique_domains == 2:
        return 0.7
    return 0.4


def _recency_score(date_text: str, topic: str = "") -> float:
    if not date_text:
        return 0.5
    # lightweight heuristic: if year appears and recent, higher score
    m = re.search(r"(20\d{2})", date_text)
    if not m:
        return 0.6
    year = int(m.group(1))
    topic_l = (topic or "").lower()
    ai_model_topic = any(token in topic_l for token in ["ai model", "foundation model", "llm", "large language", "model release", "model benchmark"])
    if year >= 2026:
        return 1.0
    if year == 2025:
        return 0.85
    if year == 2024:
        return 0.4 if ai_model_topic else 0.7
    return 0.5


def _domain_from_url(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower().replace("www.", "")
    except Exception:
        return ""


def _is_blog_domain(url: str) -> bool:
    domain = _domain_from_url(url)
    blog_markers = ["medium.com", "substack", "blog", "wordpress", "hashnode", "dev.to", "ghost.io"]
    return any(marker in domain for marker in blog_markers)


def _is_wikipedia_url(url: str) -> bool:
    domain = _domain_from_url(url)
    return "wikipedia.org" in domain


def _is_self_benchmark_claim(claim: str) -> bool:
    c = (claim or "").lower()
    benchmark_markers = ["benchmark", "accuracy", "latency", "speed", "score", "bleu", "mmlu"]
    self_markers = [
        "self-reported",
        "self validated",
        "self-validated",
        "our internal",
        "we measured",
        "in-house",
        "according to company",
        "company claims",
        "press release",
        "announced",
    ]
    return any(b in c for b in benchmark_markers) and any(s in c for s in self_markers)


def _hyperbole_score(hook: str) -> float:
    h = (hook or "").lower()
    extreme = [
        "just died",
        "is dead",
        "obliterated",
        "game over",
    ]
    strong = [
        "destroyed",
        "everyone is wrong",
        "nobody understands",
    ]
    mild = [
        "always",
        "never",
    ]
    if any(token in h for token in extreme):
        return 1.0
    if any(token in h for token in strong):
        return 0.6
    if any(token in h for token in mild):
        return 0.3
    return 0.0


def _is_hyperbolic_hook(hook: str) -> bool:
    return _hyperbole_score(hook) > 0.0


def _claim_plausibility(claim: str) -> float:
    text = (claim or "").strip().lower()
    if not text:
        return 0.4

    score = 0.75

    numbers = [float(n) for n in re.findall(r"\b\d+(?:\.\d+)?\b", text)]
    percents = [float(n) for n in re.findall(r"\b(\d+(?:\.\d+)?)\s*%", text)]
    if any(p > 200 for p in percents):
        score -= 0.35
    elif any(p > 100 for p in percents):
        score -= 0.2
    if any(n >= 1000 for n in numbers):
        score -= 0.1

    superiority_markers = [
        "beats openai",
        "better than gpt",
        "outperforms gpt",
        "best in the world",
        "state-of-the-art",
        "no one else",
        "unmatched",
    ]
    if any(marker in text for marker in superiority_markers):
        score -= 0.2

    benchmark_context_markers = ["mmlu", "gsm8k", "bleu", "f1", "auc", "benchmark", "dataset", "eval", "latency"]
    has_context = any(marker in text for marker in benchmark_context_markers)
    mentions_comparison = any(token in text for token in ["beats", "better than", "outperforms", "faster than"])
    if mentions_comparison and not has_context:
        score -= 0.15

    vague_markers = ["beats openai", "beats gpt", "faster than competitors", "better than everyone"]
    if any(marker in text for marker in vague_markers):
        score -= 0.15

    return _clamp(score, 0.0, 1.0)


def _compute_realism_components(verified_claims: list, hook_text: str) -> dict:
    if verified_claims:
        source_quality = sum(_safe_float(c.get("source_quality_weighted", c.get("source_quality", 0.0)), 0.0) for c in verified_claims) / max(len(verified_claims), 1)
        independence = sum(_safe_float(c.get("independence_score", _independence_score(int(c.get("independent_sources", 0) or 0))), 0.4) for c in verified_claims) / max(len(verified_claims), 1)
        recency = sum(_safe_float(c.get("recency", 0.5), 0.5) for c in verified_claims) / max(len(verified_claims), 1)
        plausibility = sum(_safe_float(c.get("plausibility", 0.5), 0.5) for c in verified_claims) / max(len(verified_claims), 1)
        non_self_benchmark = sum(_safe_float(c.get("non_self_benchmark", 0.3 if c.get("self_benchmark") else 1.0), 1.0) for c in verified_claims) / max(len(verified_claims), 1)
    else:
        source_quality = 0.3
        independence = 0.4
        recency = 0.5
        plausibility = 0.4
        non_self_benchmark = 0.5

    non_hyperbolic = _clamp(1.0 - _hyperbole_score(hook_text), 0.0, 1.0)
    realism_score = _clamp(
        (0.25 * source_quality)
        + (0.20 * independence)
        + (0.15 * recency)
        + (0.15 * plausibility)
        + (0.15 * non_hyperbolic)
        + (0.10 * non_self_benchmark),
        0.0,
        1.0,
    )

    return {
        "source_quality": round(source_quality, 2),
        "independence_score": round(independence, 2),
        "recency": round(recency, 2),
        "plausibility": round(plausibility, 2),
        "non_hyperbolic": round(non_hyperbolic, 2),
        "non_self_benchmark": round(non_self_benchmark, 2),
        "realism_score": round(realism_score, 2),
    }


def _soften_absolutist_hook(hook: str) -> str:
    text = (hook or "").strip()
    if not text:
        return text
    replacements = {
        " just died": " took a serious hit",
        " is dead": " is losing ground",
        " always ": " often ",
        " never ": " rarely ",
        "destroyed": "challenged",
        "obliterated": "significantly weakened",
        "game over": "a major turning point",
    }
    lowered = text.lower()
    for k, v in replacements.items():
        if k in lowered:
            pattern = re.compile(re.escape(k), re.IGNORECASE)
            text = pattern.sub(v, text)
            lowered = text.lower()
    return text


# ==========================================
# NODE 0.5: INPUT REFINEMENT
# ==========================================

def _is_gibberish_word(word: str) -> bool:
    """Check if a word appears to be keyboard smashing or nonsense."""
    word_lower = word.lower()
    
    # Keyboard pattern detection (common rows)
    keyboard_patterns = ['qwerty', 'asdf', 'zxcv', 'qwe', 'asd', 'zxc', 'wert', 'sdfg', 'xcvb']
    if any(pattern in word_lower for pattern in keyboard_patterns):
        return True
    
    # Repeated character detection (aaa, bbb, zzz)
    if len(word) >= 3 and len(set(word_lower)) == 1:
        return True
    
    # Check for excessive repeated characters (>80% same char)
    if len(word) >= 3:
        char_counts = {}
        for ch in word_lower:
            char_counts[ch] = char_counts.get(ch, 0) + 1
        max_repeats = max(char_counts.values())
        if max_repeats / len(word) > 0.8:
            return True
    
    # Low vowel ratio for longer words (less than 15% vowels)
    if len(word) >= 4:
        vowels = sum(1 for ch in word_lower if ch in 'aeiou')
        vowel_ratio = vowels / len(word)
        if vowel_ratio < 0.15:
            return True
    
    return False


def _validate_topic_quality(topic: str) -> tuple[bool, str]:
    """Validate topic quality by detecting gibberish patterns."""
    words = topic.split()
    if len(words) == 0:
        return False, "Topic is empty"
    
    # Check for repeated words (e.g., "as as", "test test test")
    unique_words = set(w.lower() for w in words if len(w) >= 2)
    if len(unique_words) == 1 and len(words) >= 2:
        return False, "Topic contains only repeated words. Please provide a meaningful topic."
    
    # Check if all words are very short (<=2 chars) - likely gibberish
    if all(len(w) <= 2 for w in words):
        return False, "Topic too vague. Please provide a clear topic with descriptive words."
    
    # Count gibberish words
    gibberish_count = sum(1 for word in words if len(word) >= 2 and _is_gibberish_word(word))
    
    # Reject if 50% or more of words are gibberish
    gibberish_ratio = gibberish_count / len(words)
    if gibberish_ratio >= 0.5:
        return False, "Topic appears to be nonsense or keyboard smashing. Please provide a meaningful topic."
    
    return True, ""


def input_refinement_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Clean or rewrite user input into a strong research topic if needed."""
    with NodeTimer("input_refinement"):
        raw_topic = (state.get("topic") or "").strip()
        if not raw_topic:
            return {"error": "Empty topic after validation"}

        # Check for gibberish patterns first
        is_valid, error_msg = _validate_topic_quality(raw_topic)
        if not is_valid:
            log_error("input_refinement", f"Gibberish detected: {raw_topic}")
            return {"error": error_msg}

        # Reject clearly nonsensical input (gibberish, too short, no meaning)
        topic_cleaned = re.sub(r"\s+", " ", raw_topic)
        word_count = len(topic_cleaned.split())
        alpha_chars = sum(1 for ch in topic_cleaned if ch.isalpha())
        digit_ratio = sum(1 for ch in topic_cleaned if ch.isdigit()) / max(len(topic_cleaned), 1)
        
        # Reject if: single char/word, too many digits, or mostly gibberish
        if word_count == 1 and len(topic_cleaned) < 3:
            log_error("input_refinement", "Topic too short - must be at least 3 characters or 2+ words")
            return {"error": "Topic too short. Please provide a clear topic (e.g., 'AI in healthcare', 'Future of remote work')"}
        
        if digit_ratio > 0.5 or alpha_chars < 3:
            log_error("input_refinement", f"Topic appears to be gibberish: {raw_topic}")
            return {"error": "Topic unclear. Please provide a meaningful topic in plain language (e.g., 'sustainable energy trends', 'startup funding strategies')"}
        
        is_good = word_count >= 3 and any(ch.isalpha() for ch in topic_cleaned)

        if _is_low_cost_mode():
            if not is_good:
                topic_cleaned = f"Latest developments in {topic_cleaned}".strip()
                is_good = True
            return {
                "topic_original": raw_topic,
                "topic": topic_cleaned,
                "topic_cleaned": topic_cleaned,
                "query_quality": 0.7 if is_good else 0.4,
                "query_rewrite_reason": "low_cost_cleanup",
            }

        prompt = f"""You are improving a research query for credible sourcing.

RAW INPUT: {raw_topic}

Return JSON only:
{{
  "cleaned_topic": "...",
  "is_good": true,
  "reason": "..."
}}

Rules:
- If the input is already specific, return it unchanged and is_good=true.
- If vague, rewrite into a specific, researchable topic without adding false facts.
- Keep it under 12 words.
"""

        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_QUERY_REFINE(),
                options={"temperature": 0.2, "num_ctx": 2048},
            )
            track_llm_call("input_refinement", response, model=MODEL_QUERY_REFINE(), purpose="Input topic refinement")
            
            parsed = _parse_json_from_llm(response)
            cleaned = (parsed.get("cleaned_topic") or topic_cleaned).strip()
            is_good = bool(parsed.get("is_good", True))
            reason = parsed.get("reason", "")
        except Exception as e:
            log_error("input_refinement", f"Query refinement failed: {e}")
            cleaned = topic_cleaned
            is_good = True
            reason = "refinement_failed"

        log_state_update("input_refinement", "topic_cleaned", cleaned)
        return {
            "topic_original": raw_topic,
            "topic": cleaned,
            "topic_cleaned": cleaned,
            "query_quality": 0.8 if is_good else 0.5,
            "query_rewrite_reason": reason,
        }


# ==========================================
# NODE 1: INPUT VALIDATION
# ==========================================
def input_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and unpack user input into state fields. Load user profile and resolve post format."""
    with NodeTimer("input_node"):
        user_input = state.get("user_input", {})

        # Validate via Pydantic
        try:
            if isinstance(user_input, dict):
                validated = PostInput(**user_input)
            else:
                validated = PostInput(topic=str(user_input))
        except Exception as e:
            log_error("input_node", f"Validation failed: {e}")
            return {"error": f"Invalid input: {e}"}

        # Load user profile
        try:
            user_persona = load_user_profile()
        except Exception as e:
            log_error("input_node", f"Profile loading failed: {e}")
            user_persona = {}

        # Resolve post format: request override > profile default > "medium"
        request_format = (validated.format or "").strip().lower()
        if request_format and request_format in FORMAT_PRESETS:
            post_format = request_format
        else:
            profile_format = user_persona.get("writing", {}).get("default_format", "medium")
            post_format = profile_format if profile_format in FORMAT_PRESETS else "medium"

        log_agent_start(validated.topic)
        log_state_update("input_node", "topic+tone+audience+goal+format", f"{validated.topic} ({post_format})")

        return {
            "user_persona": user_persona,
            "post_format": post_format,
            "topic": validated.topic,
            "tone": validated.tone,
            "audience": validated.audience,
            "goal": validated.goal,
            "include_emojis": validated.include_emojis,
            "auto_publish": validated.auto_publish,
            "iteration_count": state.get("iteration_count", 0),
            "error": "",
        }


# ==========================================
# NODE 2: STYLE MEMORY FETCH
# ==========================================
def style_memory_fetch_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch user's previous posts from pgvector to match writing style.
    
    Quality rules:
    - Only memories with cosine distance <= STYLE_MAX_DISTANCE (0.35)
    - Only past posts with distance <= STYLE_MAX_DISTANCE AND viral_score >= MIN_RETRIEVAL_SCORE
    - Rerank with cross-encoder if available, else use distance ordering
    """
    with NodeTimer("style_memory_fetch"):
        topic = state.get("topic", "")
        
        style_examples = []

        # 1. Recall from general agent memory (strict distance filter)
        try:
            raw_memories = recall_memory(topic, limit=10)
            memory_strings = []
            for item in raw_memories:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    content = str(item[0]).strip()
                    distance = float(item[1]) if item[1] else 1.0
                    # STRICT: Only semantically close memories
                    if content and distance <= MEMORY_MAX_DISTANCE:
                        memory_strings.append(content)
                elif isinstance(item, str):
                    memory_strings.append(item.strip())

            # Use memory picker to select style-relevant memories
            if memory_strings:
                picked = pick_memory_for_role(
                    query=f"LinkedIn writing style and voice for: {topic}",
                    memories=memory_strings,
                    role="writer",
                    k=3,
                )
                style_examples.extend(picked)
        except Exception as e:
            log_error("style_memory_fetch", f"Memory recall failed: {e}")

        # 2. Search past LinkedIn posts — STRICT: close match + high quality only
        try:
            query_embedding = embed_text(topic, is_query=True)
            similar_posts = search_similar_posts(
                query_embedding,
                limit=5,
                max_distance=STYLE_MAX_DISTANCE,
                min_score=MIN_RETRIEVAL_SCORE,
            )
            for post in similar_posts:
                if post.get("content"):
                    style_examples.append(post["content"][:500])
        except Exception as e:
            log_error("style_memory_fetch", f"Post search failed: {e}")

        log_state_update("style_memory_fetch", "style_examples", f"{len(style_examples)} examples found (threshold: {STYLE_MAX_DISTANCE})")
        return {"style_examples": style_examples}


# ==========================================
# NODE 3: VIRAL POSTS FETCH
# ==========================================
def viral_posts_fetch_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetch viral post templates and high-performing past posts.
    
    Quality rules:
    - Templates: distance <= VIRAL_MAX_DISTANCE (0.40)
    - Past posts: viral_score >= 7.0 only
    - Deduplicate by content similarity
    """
    with NodeTimer("viral_posts_fetch"):
        topic = state.get("topic", "")
        viral_examples = []

        try:
            query_embedding = embed_text(topic, is_query=True)

            # 1. Search viral templates — distance-gated
            templates = search_viral_templates(
                query_embedding,
                limit=5,
                max_distance=VIRAL_MAX_DISTANCE,
            )
            for t in templates:
                if t.get("content"):
                    viral_examples.append({
                        "content": t["content"][:500],
                        "hook_pattern": t.get("hook_pattern", ""),
                        "category": t.get("category", ""),
                        "score": t.get("engagement_score", 0),
                        "distance": t.get("distance", 1.0),
                    })

            # 2. Search high-scoring past posts (>= 8.0 only)
            top_posts = get_top_posts(limit=5, min_score=8.0)
            for p in top_posts:
                if p.get("content"):
                    viral_examples.append({
                        "content": p["content"][:500],
                        "hook_pattern": p.get("hook", ""),
                        "category": "past_high_performer",
                        "score": p.get("viral_score", 0),
                    })

        except Exception as e:
            log_error("viral_posts_fetch", f"Viral fetch failed: {e}")

        log_state_update("viral_posts_fetch", "viral_examples", f"{len(viral_examples)} examples found (dist<={VIRAL_MAX_DISTANCE})")
        return {"viral_examples": viral_examples}


# ==========================================
# NODE 4: TREND DISCOVERY (RAW SIGNALS)
# ==========================================
def trend_discovery_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Collect raw trend signals from Tavily without LLM summarization. Prioritize user's tech stack and industry."""
    with NodeTimer("trend_discovery"):
        topic = state.get("topic", "")
        user_persona = state.get("user_persona", {})
        previous_confidence = _safe_float(state.get("research_confidence", 1.0), 1.0)
        retry_count = int(state.get("research_retry_count", 0) or 0)
        if previous_confidence < 0.6:
            retry_count += 1
        current_month = time.strftime("%B %Y")
        
        # Extract tech stack and industry from user persona for contextual search
        tech_stack = user_persona.get("technical", {}).get("tech_stack", [])
        industry = user_persona.get("identity", {}).get("industry", "")
        tech_context = " ".join(tech_stack[:2]) if tech_stack else ""  # Use top 2 techs
        industry_context = f"in {industry}" if industry else ""

        queries = [
            f"{topic} {tech_context} funding announcement {current_month}".strip(),
            f"{topic} {tech_context} benchmark results {current_month}".strip(),
            f"{topic} {industry_context} controversy {current_month}".strip(),
            f"{topic} {tech_context} product launch {current_month}".strip(),
            f"{topic} {industry_context} real world use case {current_month}".strip(),
        ]

        trend_candidates = []
        seen_urls = set()

        for query in queries:
            result = tavily_search_structured(query=query, max_results=4)
            track_search_call("trend_discovery", query, len(result.get("results", [])))
            
            for item in result.get("results", []):
                url = (item.get("url") or "").strip()
                title = (item.get("title") or "").strip()
                snippet = (item.get("content") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                if not snippet:
                    continue
                trend_candidates.append({
                    "title": title,
                    "source": url,
                    "claim": snippet[:500],
                    "date": item.get("published_date", ""),
                    "confidence": 0.55,
                    "query": query,
                })

        trend_candidates = trend_candidates[:15]
        trend_blob = "\n".join(
            [f"- {t.get('title', '')}: {t.get('claim', '')[:220]} ({t.get('source', '')})" for t in trend_candidates[:8]]
        )

        log_state_update("trend_discovery", "trend_candidates", f"{len(trend_candidates)} raw signals")
        return {
            "trend_candidates": trend_candidates,
            "trends": trend_blob,
            "research_retry_count": retry_count,
        }


# ==========================================
# NODE 5: CLAIM EXTRACTION
# ==========================================
def claim_extraction_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Extract structured claims from raw trend candidates."""
    with NodeTimer("claim_extraction"):
        topic = state.get("topic", "")
        trend_candidates = state.get("trend_candidates", [])

        if not trend_candidates:
            return {"extracted_claims": []}

        candidates_text = "\n".join([
            f"[{idx+1}] TITLE: {c.get('title','')}\nSOURCE: {c.get('source','')}\nTEXT: {c.get('claim','')}"
            for idx, c in enumerate(trend_candidates[:12])
        ])

        prompt = f"""Extract factual claims for topic: {topic}

INPUT SIGNALS:
{candidates_text}

Output JSON only:
{{
  "claims": [
    {{
      "claim": "...",
      "type": "funding|performance|launch|controversy|adoption|opinion",
      "verifiable": "strong|weak|no",
      "source": "url",
      "date": "date if available"
    }}
  ]
}}

Rules:
- keep only concrete claims, no fluff
- max 12 claims
- preserve source url when possible
"""

        extracted_claims = []
        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_CLAIM_EXTRACT(),
                options={"temperature": 0.1, "num_ctx": 8192},
            )
            track_llm_call("claim_extraction", response, model=MODEL_CLAIM_EXTRACT(), purpose="Extract structured claims")
            
            parsed = _parse_json_from_llm(response)
            extracted_claims = parsed.get("claims", []) if isinstance(parsed.get("claims", []), list) else []
        except Exception as e:
            log_error("claim_extraction", f"Claim extraction failed: {e}")

        # deterministic fallback extraction
        if not extracted_claims:
            for c in trend_candidates[:10]:
                text = (c.get("claim") or "").strip()
                if len(text) < 30:
                    continue
                extracted_claims.append({
                    "claim": text[:260],
                    "type": "adoption",
                    "verifiable": "weak",
                    "source": c.get("source", ""),
                    "date": c.get("date", ""),
                })

        log_state_update("claim_extraction", "extracted_claims", f"{len(extracted_claims)} claims")
        return {"extracted_claims": extracted_claims[:12]}


# ==========================================
# NODE 6: FACT VERIFICATION
# ==========================================
def fact_verification_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Verify extracted claims and compute research confidence."""
    with NodeTimer("fact_verification"):
        topic = state.get("topic", "")
        extracted_claims = state.get("extracted_claims", [])
        verified_claims = []

        if not extracted_claims:
            return {
                "verified_claims": [],
                "research_confidence": 0.0,
                "research_retry_count": int(state.get("research_retry_count", 0) or 0),
            }

        for claim_obj in extracted_claims[:12]:
            claim_text = (claim_obj.get("claim") or "").strip()
            if not claim_text:
                continue

            verification_query = f"{claim_text} source news {topic}"
            verification = tavily_search_structured(query=verification_query, max_results=4)
            track_search_call("fact_verification", verification_query, len(verification.get("results", [])))
            
            source_count = int(verification.get("count", 0) or 0)
            top_results = verification.get("results", [])[:3]
            source_urls = [r.get("url", "") for r in top_results if r.get("url")]
            source_domains = [_domain_from_url(u) for u in source_urls if _domain_from_url(u)]
            independent_sources = len(set(source_domains))

            sq_scores = [_source_quality_from_url(r.get("url", "")) for r in top_results]
            source_quality = round(sum(sq_scores) / max(len(sq_scores), 1), 2)
            source_quality_weighted = round(_weighted_source_quality(source_quality, max(source_count, len(source_urls))), 2)
            independence = _independence_score(independent_sources)
            recency_scores = [_recency_score(r.get("published_date", ""), topic=topic) for r in top_results]
            recency = round(sum(recency_scores) / max(len(recency_scores), 1), 2)
            plausibility = _claim_plausibility(claim_text)
            self_benchmark = _is_self_benchmark_claim(claim_text)
            non_self_benchmark = 0.2 if self_benchmark else 1.0

            verifiable = str(claim_obj.get("verifiable", "weak")).lower()
            ver_boost = 0.05 if verifiable == "strong" else (0.02 if verifiable == "weak" else 0.0)
            claim_confidence = _clamp(
                (0.40 * source_quality_weighted)
                + (0.20 * independence)
                + (0.15 * recency)
                + (0.15 * plausibility)
                + (0.10 * non_self_benchmark)
                + ver_boost,
                0.0,
                1.0,
            )
            truth_score = claim_confidence

            entry = {
                "claim": claim_text,
                "type": claim_obj.get("type", "unknown"),
                "source": claim_obj.get("source", ""),
                "truth_score": round(truth_score, 2),
                "source_quality": source_quality,
                "source_quality_weighted": source_quality_weighted,
                "independence_score": round(independence, 2),
                "recency": recency,
                "plausibility": round(plausibility, 2),
                "claim_confidence": round(claim_confidence, 2),
                "non_self_benchmark": round(non_self_benchmark, 2),
                "source_count": source_count,
                "independent_sources": independent_sources,
                "source_urls": source_urls,
                "blog_only": bool(source_urls) and all(_is_blog_domain(u) for u in source_urls),
                "wikipedia_only": bool(source_urls) and all(_is_wikipedia_url(u) for u in source_urls),
                "self_benchmark": self_benchmark,
                "accepted": truth_score >= 0.6,
            }
            if entry["accepted"]:
                verified_claims.append(entry)

        avg_truth = round(sum(c["truth_score"] for c in verified_claims) / max(len(verified_claims), 1), 2) if verified_claims else 0.0
        coverage = _clamp(len(verified_claims) / 5.0, 0.0, 1.0)
        research_confidence = round(_clamp((0.6 * avg_truth) + (0.4 * coverage), 0.0, 1.0), 2)

        try:
            insert_research_snapshot(
                topic=topic,
                trend_candidates=state.get("trend_candidates", []),
                extracted_claims=extracted_claims,
                verified_claims=verified_claims,
                research_confidence=research_confidence,
            )
        except Exception as e:
            log_error("fact_verification", f"Persist research snapshot failed: {e}")

        log_state_update("fact_verification", "verified_claims+research_confidence", f"{len(verified_claims)} verified, confidence={research_confidence}")
        return {
            "verified_claims": verified_claims,
            "research_confidence": research_confidence,
        }


# ==========================================
# NODE 6.2: RESEARCH QUALITY ASSESSMENT
# ==========================================
def research_quality_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Compute research realism score from verified claims (pre-hook)."""
    with NodeTimer("research_quality"):
        verified_claims = state.get("verified_claims", [])
        realism = _compute_realism_components(verified_claims, "")
        realism_score = _safe_float(realism.get("realism_score", 0.0), 0.0)
        research_confidence = _safe_float(state.get("research_confidence", 0.0), 0.0)
        retries = int(state.get("research_retry_count", 0) or 0)
        max_retries = int(os.getenv("LINKEDIN_MAX_RESEARCH_RETRIES", "3"))
        min_confidence = float(os.getenv("LINKEDIN_MIN_RESEARCH_CONFIDENCE", "0.6"))
        min_realism = float(os.getenv("LINKEDIN_MIN_RESEARCH_REALISM", "0.6"))

        log_state_update("research_quality", "research_realism_score", f"{realism_score}")
        if retries >= max_retries and (research_confidence < min_confidence or realism_score < min_realism):
            log_error(
                "research_quality",
                f"FAILED_GATE: confidence={research_confidence}, realism={realism_score}, retries={retries}/{max_retries}",
            )
            return {
                "research_realism_score": realism_score,
                "approval_status": "rejected",
                "error": f"rejected_due_to_low_research_quality:confidence={research_confidence},realism={realism_score}",
            }

        return {"research_realism_score": realism_score}


# ==========================================
# NODE 6.3: SOURCE-AWARE QUERY GENERATOR
# ==========================================
def source_query_generator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate targeted research queries based on weak evidence."""
    with NodeTimer("source_query_generator"):
        topic = state.get("topic", "")
        verified_claims = state.get("verified_claims", [])
        risk_flags = state.get("risk_flags", [])

        base_queries = [
            f"{topic} Reuters",
            f"{topic} Bloomberg",
            f"{topic} Financial Times",
            f"{topic} arxiv preprint",
            f"{topic} GitHub repository",
        ]

        if _is_low_cost_mode():
            queries = base_queries
            for claim in verified_claims[:4]:
                claim_text = (claim.get("claim") or "").strip()
                if claim_text:
                    queries.append(f"{claim_text} independent source")
            if "controversy" in risk_flags:
                queries.append(f"{topic} regulator investigation")
            return {"research_queries": queries[:12]}

        claims_blob = "\n".join([f"- {c.get('claim', '')}" for c in verified_claims[:6]]) or "None"
        prompt = f"""Create targeted research queries for independent verification.

TOPIC: {topic}
VERIFIED CLAIMS:
{claims_blob}

Return JSON only:
{{
  "queries": ["...", "...", "..."]
}}

Rules:
- 6 to 10 queries
- Mix independent news sources and primary research (e.g., Reuters, Bloomberg, FT, arXiv, GitHub)
- Keep each query under 12 words
- Avoid repeating the same phrasing
"""

        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_QUERY_GEN(),
                options={"temperature": 0.3, "num_ctx": 2048},
            )
            parsed = _parse_json_from_llm(response)
            queries = parsed.get("queries", []) if isinstance(parsed.get("queries"), list) else []
        except Exception as e:
            log_error("source_query_generator", f"Query generation failed: {e}")
            queries = base_queries

        merged = []
        seen = set()
        for q in (queries + base_queries):
            if not isinstance(q, str):
                continue
            q = q.strip()
            key = q.lower()
            if not q or key in seen:
                continue
            seen.add(key)
            merged.append(q)
        return {"research_queries": merged[:12]}


# ==========================================
# NODE 6.4: TARGETED RE-SEARCH
# ==========================================
def targeted_research_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Run targeted research queries and merge results into trend candidates."""
    with NodeTimer("targeted_research"):
        topic = state.get("topic", "")
        queries = state.get("research_queries", [])
        existing = state.get("trend_candidates", [])

        if not queries:
            return {"trend_candidates": existing, "trends": state.get("trends", "")}

        trend_candidates = list(existing)
        seen_urls = {c.get("source") for c in existing if c.get("source")}

        for query in queries[:12]:
            result = tavily_search_structured(query=query, max_results=4)
            for item in result.get("results", [])[:4]:
                url = (item.get("url") or "").strip()
                title = (item.get("title") or "").strip()
                snippet = (item.get("content") or "").strip()
                if not url or url in seen_urls or not snippet:
                    continue
                seen_urls.add(url)
                trend_candidates.append({
                    "title": title,
                    "source": url,
                    "claim": snippet[:500],
                    "date": item.get("published_date", ""),
                    "confidence": 0.6,
                    "query": query,
                })

        trend_candidates = trend_candidates[:20]
        trend_blob = "\n".join(
            [f"- {t.get('title', '')}: {t.get('claim', '')[:220]} ({t.get('source', '')})" for t in trend_candidates[:10]]
        )

        log_state_update("targeted_research", "trend_candidates", f"{len(trend_candidates)} merged signals")
        return {
            "trend_candidates": trend_candidates,
            "trends": trend_blob,
            "research_retry_count": int(state.get("research_retry_count", 0) or 0) + 1,
        }


# ==========================================
# NODE 6.5: CONTRADICTION ENGINE
# ==========================================
def contradiction_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Search for counter-claims and controversy signals to balance confirmation bias."""
    with NodeTimer("contradiction"):
        topic = state.get("topic", "")
        verified_claims = state.get("verified_claims", [])
        counter_claims = []
        risk_flags = set()

        if not verified_claims:
            return {
                "counter_claims": [],
                "risk_flags": [],
                "controversy_score": 0.0,
                "confidence_adjustment": 0.0,
            }

        controversy_hits = 0
        total_checks = 0
        keyword_markers = ["criticism", "controversy", "debate", "backlash", "lawsuit", "regulator", "antitrust", "ethics", "bias", "safety", "recall"]

        for claim_obj in verified_claims[:8]:
            claim_text = (claim_obj.get("claim") or "").strip()
            if not claim_text:
                continue

            queries = [
                f"{claim_text} criticism",
                f"{topic} controversy",
                f"{claim_text} debate",
            ]

            for query in queries:
                total_checks += 1
                result = tavily_search_structured(query=query, max_results=3)
                for item in result.get("results", [])[:3]:
                    snippet = (item.get("content") or "").strip()
                    title = (item.get("title") or "").strip()
                    url = (item.get("url") or "").strip()
                    if not snippet:
                        continue

                    text_blob = f"{title} {snippet}".lower()
                    has_risk = any(marker in text_blob for marker in keyword_markers)
                    if has_risk:
                        controversy_hits += 1
                        risk_flags.add("controversy")

                    counter_claims.append({
                        "claim": claim_text,
                        "query": query,
                        "title": title,
                        "source": url,
                        "snippet": snippet[:320],
                        "date": item.get("published_date", ""),
                        "domain": _domain_from_url(url),
                        "risk_signal": has_risk,
                    })

        controversy_score = _clamp(controversy_hits / max(total_checks, 1), 0.0, 1.0)
        if controversy_score >= 0.6:
            confidence_adjustment = -0.2
        elif controversy_score >= 0.3:
            confidence_adjustment = -0.1
        else:
            confidence_adjustment = 0.0

        research_confidence = _safe_float(state.get("research_confidence", 0.0), 0.0)
        research_confidence = round(_clamp(research_confidence + confidence_adjustment, 0.0, 1.0), 2)

        log_state_update(
            "contradiction",
            "counter_claims+controversy_score",
            f"{len(counter_claims)} counters, controversy={controversy_score}",
        )

        return {
            "counter_claims": counter_claims[:25],
            "risk_flags": sorted(risk_flags),
            "controversy_score": round(controversy_score, 2),
            "confidence_adjustment": confidence_adjustment,
            "research_confidence": research_confidence,
        }


# ==========================================
# NODE 7: ANGLE BUILDER
# ==========================================
def angle_builder_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Build a high-authority content angle from verified facts. Tailor to user's job role and industry."""
    with NodeTimer("angle_builder"):
        topic = state.get("topic", "")
        audience = state.get("audience", "tech professionals")
        user_persona = state.get("user_persona", {})
        verified_claims = state.get("verified_claims", [])
        
        # Extract persona context for angle tailoring
        job_role = user_persona.get("identity", {}).get("job_role", "")
        industry = user_persona.get("identity", {}).get("industry", "")
        years_exp = user_persona.get("identity", {}).get("years_experience", 0)

        if not verified_claims:
            fallback = {
                "best_angle": f"Most teams are underestimating the second-order impact of {topic}.",
                "angle_type": "market_shift",
                "supporting_facts": [],
                "risk_level": "high",
            }
            return {"angle_package": fallback}

        facts_blob = "\n".join([
            f"- {c.get('claim')} (truth={c.get('truth_score')}, source_quality={c.get('source_quality')}, recency={c.get('recency')})"
            for c in verified_claims[:8]
        ])
        
        # Build persona context for prompt
        persona_ctx = f"""You are a {job_role} with {years_exp} years of experience in {industry}.""" if job_role else ""

        prompt = f"""You are an elite thought-leadership strategist.
Build a strong, defensible LinkedIn angle grounded in industry insight, not company-specific branding.

{persona_ctx}

TOPIC: {topic}
AUDIENCE: {audience}

VERIFIED FACTS:
{facts_blob}

Output JSON only:
{{
  "best_angle": "single sharp thesis",
  "angle_type": "contrarian|founder_lesson|market_shift|tactical_insight|prediction",
  "supporting_facts": ["fact1", "fact2", "fact3"],
  "risk_level": "low|med|high"
}}

Rules:
- Avoid absolutist language like "dead", "always", "never", "everyone", "nobody"
- Prefer credible framing such as "took a serious hit", "is losing ground", "often", "many"
- If confidence is mixed, reflect uncertainty without becoming weak
- Frame insights as industry-wide patterns, not tied to a single company
- Generalize operational success stories: use "When teams implement X" instead of "At CompanyY we did X"
"""

        angle_package = {}
        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_ANGLE(),
                options={"temperature": 0.4, "num_ctx": 8192},
            )
            parsed = _parse_json_from_llm(response)
            angle_package = {
                "best_angle": parsed.get("best_angle", ""),
                "angle_type": parsed.get("angle_type", "market_shift"),
                "supporting_facts": parsed.get("supporting_facts", []),
                "risk_level": parsed.get("risk_level", "med"),
            }
        except Exception as e:
            log_error("angle_builder", f"Angle generation failed: {e}")

        if not angle_package.get("best_angle"):
            top_claims = [c.get("claim", "") for c in verified_claims[:3] if c.get("claim")]
            angle_package = {
                "best_angle": f"The real story in {topic} is execution quality, not headline hype.",
                "angle_type": "founder_lesson",
                "supporting_facts": top_claims,
                "risk_level": "med",
            }

        log_state_update("angle_builder", "angle_package", f"{angle_package.get('angle_type', 'unknown')} | risk={angle_package.get('risk_level', 'med')}")
        return {"angle_package": angle_package}


# ==========================================
# NODE 7.5: AUTHORITY POV BUILDER
# ==========================================
def pov_builder_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate an insider POV to strengthen authority tone. Tailor to user's job role and industry."""
    with NodeTimer("pov_builder"):
        topic = state.get("topic", "")
        angle_package = state.get("angle_package", {})
        risk_flags = state.get("risk_flags", [])
        verified_claims = state.get("verified_claims", [])
        controversy_score = _safe_float(state.get("controversy_score", 0.0), 0.0)
        user_persona = state.get("user_persona", {})
        
        # Extract persona context
        job_role = user_persona.get("identity", {}).get("job_role", "engineer")
        industry = user_persona.get("identity", {}).get("industry", "tech")
        organization = user_persona.get("identity", {}).get("organization", "")

        if _is_low_cost_mode():
            pov_package = {
                "founder_pov": f"If I were building in {topic}, I would optimize for verification, not headlines.",
                "insider_framing": "Most public takes skip the tradeoffs that matter in production.",
                "strong_stance": "The uncomfortable truth: credibility beats velocity when the stakes are real.",
            }
            return {"pov_package": pov_package}

        facts_blob = "\n".join([f"- {c.get('claim', '')}" for c in verified_claims[:6]]) or "None"
        angle_ctx = json.dumps(angle_package, ensure_ascii=False) if angle_package else "None"
        
        # Build role-specific framing
        role_framing = f"You are a senior {job_role} working in {industry}."
        org_context = f" (similar context to {organization})" if organization else ""

        prompt = f"""
You are synthesizing a memo of authoritative industry insight about {topic}.

{role_framing}{org_context}

TOPIC: {topic}
ANGLE: {angle_ctx}
VERIFIED FACTS:
{facts_blob}
RISK FLAGS: {", ".join(risk_flags) if risk_flags else "none"}
CONTROVERSY SCORE: {controversy_score}

Answer with authoritative insight from a senior {job_role} perspective in the {industry} sector:
- What does the industry consensus get wrong about this?
- What is the uncomfortable truth most leaders avoid saying publicly?
- How do high-performing teams in {industry} actually handle this challenge?

Return JSON only - frame insights as industry patterns, not company-specific observations:
{{
  "founder_pov": "...",
  "insider_framing": "...",
  "strong_stance": "..."
}}"""

        pov_package = {}
        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_POV(),
                options={"temperature": 0.5, "num_ctx": 4096},
            )
            parsed = _parse_json_from_llm(response)
            pov_package = {
                "founder_pov": parsed.get("founder_pov", ""),
                "insider_framing": parsed.get("insider_framing", ""),
                "strong_stance": parsed.get("strong_stance", ""),
            }
        except Exception as e:
            log_error("pov_builder", f"POV generation failed: {e}")

        if not pov_package.get("founder_pov"):
            pov_package = {
                "founder_pov": f"The real risk in {topic} is miscalibrated confidence, not missing a trend.",
                "insider_framing": "Most teams do not talk about the operational debt these decisions create.",
                "strong_stance": "The uncomfortable truth: without independent validation, you are just trading on hype.",
            }

        log_state_update("pov_builder", "pov_package", "insider framing added")
        return {"pov_package": pov_package}


# ==========================================
# NODE 5: HOOK GENERATOR
# ==========================================
def hook_generator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate 5 hook types and select the best one."""
    with NodeTimer("hook_generator"):
        topic = state.get("topic", "")
        tone = state.get("tone", "professional")
        trends = state.get("trends", "")
        verified_claims = state.get("verified_claims", [])
        angle_package = state.get("angle_package", {})
        pov_package = state.get("pov_package", {})
        style_examples = state.get("style_examples", [])
        viral_examples = state.get("viral_examples", [])
        include_emojis = state.get("include_emojis", False)
        score_feedback = state.get("score_feedback", {})
        iteration_count = int(state.get("iteration_count", 0) or 0)

        if _is_low_cost_mode():
            selected_hook = f"Here's what most people miss about {topic}."
            hooks = [{"type": "low_cost", "text": selected_hook, "strength_score": 6}]
            log_state_update("hook_generator", "hooks+selected_hook", f"{len(hooks)} hooks (low-cost mode)")
            return {"hooks": hooks, "selected_hook": selected_hook}

        # Build context
        style_ctx = "\n".join([f"- {s[:200]}" for s in style_examples[:3]]) if style_examples else "None available"
        viral_ctx = ""
        for v in viral_examples[:3]:
            if isinstance(v, dict):
                viral_ctx += f"- Hook: {v.get('hook_pattern', 'N/A')} | Score: {v.get('score', 'N/A')}\n  Content: {v.get('content', '')[:200]}\n"
            else:
                viral_ctx += f"- {str(v)[:200]}\n"
        if not viral_ctx:
            viral_ctx = "None available"

        emoji_instruction = "Include relevant emojis where appropriate." if include_emojis else "Do NOT use any emojis."
        claims_ctx = "\n".join([
            f"- {c.get('claim', '')} (truth={c.get('truth_score', 0)}, recency={c.get('recency', 0)})"
            for c in verified_claims[:6]
        ]) or "None"
        angle_ctx = json.dumps(angle_package, ensure_ascii=False) if angle_package else "None"
        pov_ctx = json.dumps(pov_package, ensure_ascii=False) if pov_package else "None"
        feedback_ctx = ""
        if score_feedback:
            weakest = ", ".join(score_feedback.get("weakest_dimensions", [])[:3])
            suggestions = "\n".join([f"- {s}" for s in score_feedback.get("improvement_suggestions", [])[:5]])
            feedback_ctx = f"""

    ### PREVIOUS ITERATION FEEDBACK (must fix now):
    Weakest dimensions: {weakest or 'N/A'}
    Specific fixes:
    {suggestions or '- Increase specificity and practical value'}
    """

        prompt = f"""{MASTER_PROMPT}

### TASK: Generate 5 scroll-stopping LinkedIn hooks

TOPIC: {topic}
TONE: {tone}
{emoji_instruction}

### CURRENT TRENDS:
{trends[:500]}

### VERIFIED CLAIMS (use these, avoid unsupported stats):
{claims_ctx}

### ANGLE PACKAGE (prioritize this POV):
{angle_ctx}

### INSIDER POV (use this voice for authority):
{pov_ctx}

### STYLE REFERENCES (mirror this voice):
{style_ctx}

### VIRAL REFERENCES (learn these patterns):
{viral_ctx}

{feedback_ctx}

### HOOK TYPES TO GENERATE:
1. CURIOSITY GAP — Create an information vacuum the reader MUST fill. 
   Pattern: State an unexpected outcome, withhold the "how".
   Example: "I mass-deleted 200 LinkedIn connections last month. My engagement tripled."

2. AUTHORITY CLAIM — Lead with a specific credential or result that earns instant trust.
   Pattern: Number + timeframe + result.
   Example: "After mass-hiring 47 engineers in 6 months, here's what actually predicts success."

3. CONTRARIAN STRIKE — Challenge a belief your audience holds sacred. Be bold, not reckless.
   Pattern: "[Popular belief] is wrong. Here's the data."
   Example: "Stop telling junior devs to 'just build projects.' It's the worst advice in tech."

4. MICRO-STORY — Drop the reader into a vivid scene in 2 lines. Sensory details matter.
   Pattern: Time + place + unexpected action.
   Example: "My CTO called me at 2 AM. 'We're rolling back everything.' Here's what happened."

5. POLARIZING QUESTION — Frame a genuine either/or that forces the reader to pick a side.
   Pattern: Present two options where smart people disagree.
   Example: "Unpopular opinion: 10x engineers don't exist. But 0.1x environments do."

### SCORING EACH HOOK (be brutally honest):
Rate each 1-10 where:
- 1-3: Generic, forgettable, could be about anything
- 4-5: Decent but won't stop the scroll
- 6-7: Strong, specific, makes you want to read more
- 8-9: Exceptional, would get shared
- 10: Once-in-a-month viral hook

DO NOT give every hook a 7. Most hooks are 4-6. Only rate 8+ if it's genuinely exceptional.

### CREDIBILITY RULE:
- Avoid absolutist/hyperbolic phrasing ("just died", "is dead", "always", "never", "everyone is wrong").
- Use credible framing that remains strong but defensible.

### OUTPUT (valid JSON only):
{{
  "hooks": [
    {{"type": "curiosity", "text": "...", "strength_score": 6.5}},
    {{"type": "authority", "text": "...", "strength_score": 4.0}},
    {{"type": "contrarian", "text": "...", "strength_score": 8.0}},
    {{"type": "storytelling", "text": "...", "strength_score": 5.5}},
    {{"type": "debate", "text": "...", "strength_score": 7.0}}
  ],
  "best_hook_index": 2,
  "reason": "This hook works because [specific reason tied to the topic and audience]"
}}"""

        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_HOOK_GEN(),
                options={"temperature": 0.7, "num_ctx": 4096},
            )

            parsed = _parse_json_from_llm(response)
            hooks = parsed.get("hooks", [])
            if not hooks and isinstance(parsed.get("items"), list):
                hooks = parsed.get("items", [])
            best_idx = parsed.get("best_hook_index", 0)

            # Handle non-JSON / malformed outputs common in local LLMs
            if not hooks:
                extracted = _extract_hook_candidates(response, topic)
                hooks = [
                    {"type": f"candidate_{idx + 1}", "text": text, "strength_score": 5.0}
                    for idx, text in enumerate(extracted)
                ]

            # If model returns too few hooks, run compact recovery pass
            if len(hooks) < 5:
                recovery_prompt = f"""Generate exactly 5 LinkedIn hooks for topic: {topic}\n\nReturn valid JSON only in this shape:\n{{\"hooks\":[\"hook 1\",\"hook 2\",\"hook 3\",\"hook 4\",\"hook 5\"]}}\n\nRules:\n- each hook 8-18 words\n- no intro text\n- no markdown\n- no emojis"""
                recovery_raw = chat(
                    messages=[{"role": "user", "content": recovery_prompt}],
                    model=MODEL_HOOK_GEN(),
                    options={"temperature": 0.6, "num_ctx": 2048},
                )
                recovered = _parse_json_from_llm(recovery_raw)
                recovered_hooks = recovered.get("hooks", [])
                if isinstance(recovered_hooks, list) and recovered_hooks:
                    merged = []
                    for item in recovered_hooks:
                        if isinstance(item, str):
                            merged.append({"type": "recovered", "text": item, "strength_score": 5.0})
                        elif isinstance(item, dict):
                            merged.append({
                                "type": item.get("type", "recovered"),
                                "text": item.get("text", ""),
                                "strength_score": item.get("strength_score", 5.0),
                            })
                    hooks.extend([h for h in merged if h.get("text")])

            # Final cleanup + dedupe + cap
            normalized = []
            seen = set()
            for hook in hooks:
                if isinstance(hook, str):
                    hook = {"type": "candidate", "text": hook, "strength_score": 5.0}
                text = (hook.get("text", "") or "").strip()
                if not text:
                    continue
                key = re.sub(r"\W+", "", text.lower())
                if not key or key in seen:
                    continue
                seen.add(key)
                normalized.append({
                    "type": hook.get("type", "candidate"),
                    "text": text,
                    "strength_score": float(hook.get("strength_score", 5.0)),
                })

            if len(normalized) < 5:
                extracted = _extract_hook_candidates(response, topic)
                for text in extracted:
                    key = re.sub(r"\W+", "", text.lower())
                    if key not in seen:
                        normalized.append({"type": "fallback", "text": text, "strength_score": 5.0})
                        seen.add(key)
                    if len(normalized) >= 5:
                        break

            hooks = normalized[:5]

            if hooks and 0 <= best_idx < len(hooks):
                selected_hook = hooks[best_idx].get("text", "")
            elif hooks:
                # Fallback: pick highest score
                hooks_sorted = sorted(hooks, key=lambda h: h.get("strength_score", 0), reverse=True)
                selected_hook = hooks_sorted[0].get("text", "")
            else:
                selected_hook = f"Here's something most people get wrong about {topic}."
                hooks = [{"type": "fallback", "text": selected_hook, "strength_score": 5}]

            selected_hook = _soften_absolutist_hook(selected_hook)

        except Exception as e:
            log_error("hook_generator", f"Hook generation failed: {e}")
            selected_hook = f"Here's something most people get wrong about {topic}."
            hooks = [{"type": "fallback", "text": selected_hook, "strength_score": 5}]

        next_iteration = iteration_count + 1
        
        # Update context variable for usage tracking
        from brain.logger import set_iteration_count
        set_iteration_count(next_iteration)
        
        log_state_update("hook_generator", "hooks+selected_hook", f"iter {next_iteration}: {len(hooks)} hooks, best: {selected_hook[:50]}...")
        return {"hooks": hooks, "selected_hook": selected_hook, "iteration_count": next_iteration}


# ==========================================
# NODE 6: POST WRITER (MAIN BRAIN)
# ==========================================
def post_writer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Write the full LinkedIn post using all gathered context. Tailor to user persona and post format."""
    with NodeTimer("post_writer"):
        topic = state.get("topic", "")
        tone = state.get("tone", "professional")
        audience = state.get("audience", "tech professionals")
        goal = state.get("goal", "engagement")
        include_emojis = state.get("include_emojis", False)
        selected_hook = state.get("selected_hook", "")
        trends = state.get("trends", "")
        verified_claims = state.get("verified_claims", [])
        angle_package = state.get("angle_package", {})
        pov_package = state.get("pov_package", {})
        style_examples = state.get("style_examples", [])
        viral_examples = state.get("viral_examples", [])
        hooks = state.get("hooks", [])
        score_feedback = state.get("score_feedback", {})
        user_persona = state.get("user_persona", {})
        post_format = state.get("post_format", "medium")

        realism = _compute_realism_components(verified_claims, selected_hook)
        if realism.get("realism_score", 0.0) < 0.6:
            log_error("realism_check", f"FAILED: Score {realism.get('realism_score')} is too low.")
            thought_piece = {
                "hook": selected_hook or f"Most people talk about {topic} outcomes, not evidence.",
                "post": (
                    f"{selected_hook or f'Most people talk about {topic} outcomes, not evidence.'}\n\n"
                    f"There is a real signal here, but the public data is still thin.\n\n"
                    "If I were advising a team, I would pause before repeating numbers we cannot verify.\n\n"
                    "The uncomfortable truth: credibility compounds slower than hype, but it wins.\n\n"
                    "Have you ever held back a hot take because the evidence was not strong enough?"
                ),
                "cta": "Have you ever held back a hot take because the evidence was not strong enough?",
                "hashtags": ["#Leadership", "#AI"],
                "viral_score_prediction": 4.0,
                "reasoning": "Low realism score triggered thought-piece fallback to avoid unsupported claims.",
            }
            return {
                "generated_post": thought_piece,
                "approval_status": "rejected",
                "error": f"rejected_due_to_low_realism:{realism.get('realism_score')}",
            }

        # Build context blocks
        style_ctx = "\n".join([f"- {s[:300]}" for s in style_examples[:3]]) if style_examples else "None"
        viral_ctx = ""
        for v in viral_examples[:3]:
            if isinstance(v, dict):
                viral_ctx += f"- {v.get('content', '')[:300]}\n"
            else:
                viral_ctx += f"- {str(v)[:300]}\n"
        if not viral_ctx:
            viral_ctx = "None"

        hooks_ctx = "\n".join([
            f"- [{h.get('type', 'unknown')}] {h.get('text', '')}"
            for h in hooks[:5]
        ]) if hooks else "None"

        emoji_instruction = "Include relevant emojis where they add value." if include_emojis else "Do NOT use any emojis."
        claims_ctx = "\n".join([
            f"- {c.get('claim', '')} (truth={c.get('truth_score', 0)}, source_quality={c.get('source_quality', 0)}, recency={c.get('recency', 0)})"
            for c in verified_claims[:8]
        ]) or "None"
        angle_ctx = json.dumps(angle_package, ensure_ascii=False) if angle_package else "None"
        pov_ctx = json.dumps(pov_package, ensure_ascii=False) if pov_package else "None"
        
        # Extract persona context for prompt
        job_role = user_persona.get("identity", {}).get("job_role", "")
        organization = user_persona.get("identity", {}).get("organization", "")
        years_exp = user_persona.get("identity", {}).get("years_experience", 0)
        industry = user_persona.get("identity", {}).get("industry", "")
        tech_stack = user_persona.get("technical", {}).get("tech_stack", [])
        expertise_level = user_persona.get("technical", {}).get("expertise_level", "intermediate")
        use_jargon = user_persona.get("writing", {}).get("use_technical_jargon", False)
        
        # Build persona context block for prompt
        persona_ctx = f"""AUTHOR CONTEXT:
- Role: {job_role or 'Tech Professional'}
- Industry/Sector: {industry or 'Technology'}
- Experience: {years_exp} years
- Tech Stack: {', '.join(tech_stack[:3]) if tech_stack else 'Not specified'}
- Expertise Level: {expertise_level.title()}
- Jargon Preference: {"Uses technical terminology" if use_jargon else "Prefers accessible explanations"}

Write as if YOU are this person sharing from your authentic experience in this sector.
Frame examples and lessons as industry-wide insights, not tied to your employer.
Anonymize company-specific successes as general patterns or methodologies."""
        
        # Get format-specific instructions
        format_instructions = get_format_prompt_section(post_format)
        
        feedback_ctx = ""
        if score_feedback:
            weakest = ", ".join(score_feedback.get("weakest_dimensions", [])[:4])
            suggestions = "\n".join([f"- {s}" for s in score_feedback.get("improvement_suggestions", [])[:6]])
            feedback_ctx = f"""

    ### MANDATORY FIXES FROM PREVIOUS SCORE:
    Weakest dimensions: {weakest or 'N/A'}
    Apply these fixes explicitly:
    {suggestions or '- Improve specificity, value density, and CTA quality'}
    """

        prompt = f"""{MASTER_PROMPT}

{persona_ctx}

### TASK: Write a complete LinkedIn post

TOPIC: {topic}
TONE: {tone}
TARGET AUDIENCE: {audience}
PRIMARY GOAL: {goal}
{emoji_instruction}

### FORMAT REQUIREMENTS:
{format_instructions}

### SELECTED HOOK (start with this — you may refine it slightly):
{selected_hook}

### CURRENT TRENDS (weave in naturally, don't force):
{trends[:500]}

### VERIFIED FACTS (MUST anchor claims to these):
{claims_ctx}

### STRATEGIC ANGLE (follow this thesis):
{angle_ctx}

### INSIDER POV (tone authority from this):
{pov_ctx}

### STYLE REFERENCES (match this voice and rhythm):
{style_ctx}

### VIRAL REFERENCES (learn structural patterns, don't copy):
{viral_ctx}

### ALL HOOKS GENERATED (for additional inspiration):
{hooks_ctx}

{feedback_ctx}

### POST STRUCTURE TO FOLLOW (adapted for {post_format} format):
1. HOOK (lines 1-2): The selected hook. Must work in LinkedIn preview (first ~210 chars visible before "...see more").
2. TENSION (lines 3-6): Build the problem, story, or counterintuitive setup. Create a gap between what the reader believes and what's true.
3. INSIGHT (lines 7-12): Deliver the core value. Be specific — use numbers, tools, methodologies, timelines, real examples. This is where you earn the save/bookmark.
4. PROOF/STORY (lines 13-16): One concrete example or case study that validates the insight. Frame as industry pattern: "When teams implement X → Y typically happens" or "Most major deployments fail because..." (NOT "I did X at CompanyY").
5. CTA (last 2 lines): Ask a SPECIFIC question tied to the content. Not "What do you think?" but "Have you ever faced [specific scenario]? How did you handle it?"
6. KNOWLEDGE + EMOTION: Include at least one concrete fact/metric/tool/methodology and at least one emotional sentence (frustration, fear, relief, conviction, excitement).
7. TAKEAWAY: Include one practical mini-framework/list of exactly 3 short points in the second half of the post.

### ANONYMIZATION RULES:
- NEVER mention your company name, employer, or specific company examples
- Transform company wins into industry patterns: "At CompanyX we cut latency 30%" → "Implementing prompt caching via FastAPI can slash latency by 30%"
- Use generalizing language: "When teams...", "Most successful deployments...", "For instance..." instead of "I saw", "We did", "At my company"
- Keep the authority grounded in methodologies and practices, not company-specific anecdotes

### FORMATTING RULES:
- Target {get_format_preset(post_format)["word_range"][0]}-{get_format_preset(post_format)["word_range"][1]} words total
- Single blank line between every paragraph
- Paragraphs: 1-3 sentences max
- No bullet points in the first half (for short/medium formats)
- Hashtags: exactly 2-3, placed at the very end after a blank line

### REALISM RULES:
- Do not invent funding numbers, benchmark values, or named partnerships not present in VERIFIED FACTS
- If evidence is weak, express uncertainty explicitly
- Do not reference specific company names unless they appear in VERIFIED FACTS

### SELF-CHECK BEFORE RESPONDING:
Before writing your JSON output, mentally verify:
□ Does line 1 create a curiosity gap or pattern interrupt?
□ Would you personally stop scrolling for this?
□ Is there at least one specific number, name, or data point?
□ Does the CTA ask something people will WANT to answer?
□ Is it under {get_format_preset(post_format)["word_range"][1]} words?

### OUTPUT FORMAT (valid JSON only):
{{
  "hook": "the opening 1-2 lines verbatim",
  "post": "the FULL post body including hook through CTA. Use \\n for line breaks.",
  "cta": "the closing call-to-action (also included at end of post field)",
  "hashtags": ["hashtag1", "hashtag2"],
  "viral_score_prediction": 6.0,
  "reasoning": "2-3 sentences: What specific elements make this post strong or weak? Be honest."
}}

IMPORTANT: viral_score_prediction must be your HONEST assessment:
- 3-4: Decent but forgettable
- 5-6: Solid, will get some engagement  
- 7-8: Strong, likely to go semi-viral
- 9-10: Exceptional (rate this only if you genuinely believe it)
Do NOT default to 7.5. Most posts are 5-6."""

        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_WRITER(),
                options={"temperature": 0.7, "num_ctx": 8192},
            )
            track_llm_call("post_writer", response, model=MODEL_WRITER(), purpose="Generate LinkedIn post")

            generated_post = _parse_json_from_llm(response)

            # Validate minimum fields
            if not generated_post.get("post"):
                raise ValueError("LLM returned empty post body")

            # Ensure required fields exist
            generated_post.setdefault("hook", selected_hook)
            generated_post.setdefault("cta", "What do you think? Drop your take below.")
            generated_post.setdefault("hashtags", [])
            generated_post.setdefault("viral_score_prediction", 5.0)
            generated_post.setdefault("reasoning", "")

            # Local LLM guardrail: enforce minimum depth and non-generic CTA
            current_post = generated_post.get("post", "")
            wc = _word_count(current_post)

            if wc < 170 or _is_generic_cta(generated_post.get("cta", "")):
                expand_prompt = f"""Improve this LinkedIn draft without changing its core idea.

Requirements:
- Final length: 180-260 words
- Keep same hook theme
- Add one concrete metric/company/tool reference
- Add one emotional sentence
- Add one 3-point practical takeaway in second half
- Replace generic CTA with specific either/or or fill-in-the-blank CTA
- Keep mobile-friendly short paragraphs

Return valid JSON only:
{{
  "hook": "...",
  "post": "...",
  "cta": "...",
  "hashtags": ["...", "..."],
  "viral_score_prediction": 6.0,
  "reasoning": "..."
}}

Current draft:
{json.dumps(generated_post, ensure_ascii=False)}"""

                expanded_raw = chat(
                    messages=[{"role": "user", "content": expand_prompt}],
                    model=MODEL_WRITER(),
                    options={"temperature": 0.5, "num_ctx": 8192},
                )
                track_llm_call("post_writer", expanded_raw, model=MODEL_WRITER(), purpose="Expand short post")
                
                expanded = _parse_json_from_llm(expanded_raw)
                if expanded.get("post") and _word_count(expanded.get("post", "")) >= 170:
                    generated_post.update({
                        "hook": expanded.get("hook", generated_post.get("hook", selected_hook)),
                        "post": expanded.get("post", generated_post.get("post", "")),
                        "cta": expanded.get("cta", generated_post.get("cta", "")),
                        "hashtags": expanded.get("hashtags", generated_post.get("hashtags", [])),
                        "viral_score_prediction": expanded.get("viral_score_prediction", generated_post.get("viral_score_prediction", 5.0)),
                        "reasoning": expanded.get("reasoning", generated_post.get("reasoning", "")),
                    })

        except Exception as e:
            log_error("post_writer", f"Post writing failed: {e}")
            generated_post = {
                "hook": selected_hook,
                "post": f"{selected_hook}\n\n{topic} is changing faster than most people realize.\n\nThe ones who adapt now will have an unfair advantage.\n\nWhat's your take?",
                "cta": "What's your take? Comment below.",
                "hashtags": ["#Technology", "#LinkedIn"],
                "viral_score_prediction": 4.0,
                "reasoning": "Fallback post generated due to LLM error",
            }

        log_state_update("post_writer", "generated_post", f"{len(generated_post.get('post', ''))} chars")
        return {"generated_post": generated_post}


# ==========================================
# NODE 7: ENGAGEMENT OPTIMIZER
# ==========================================
def engagement_optimizer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Optimize the post for engagement: readability, CTA, spacing, punchlines. Apply format-specific refinements."""
    with NodeTimer("engagement_optimizer"):
        generated_post = state.get("generated_post", {})
        tone = state.get("tone", "professional")
        audience = state.get("audience", "tech professionals")
        include_emojis = state.get("include_emojis", False)
        post_format = state.get("post_format", "medium")
        user_persona = state.get("user_persona", {})

        original_post = generated_post.get("post", "")
        original_cta = generated_post.get("cta", "")
        original_hook = generated_post.get("hook", "")
        score_feedback = state.get("score_feedback", {})

        if _is_low_cost_mode():
            optimized = generated_post.copy()
            if not optimized.get("reasoning"):
                optimized["reasoning"] = "Low-cost mode: skipped optimizer to save LLM quota"
            log_state_update("engagement_optimizer", "optimized_post", "post kept (low-cost mode)")
            return {"optimized_post": optimized}

        emoji_instruction = "Add 1-2 relevant emojis per section if they add value." if include_emojis else "Remove ALL emojis if any exist."
        
        # Get format-specific guidance
        fmt_preset = get_format_preset(post_format)
        word_min, word_max = fmt_preset["word_range"]
        format_guidance = f"""
### FORMAT-SPECIFIC OPTIMIZATION ({post_format.upper()} format):
- Target word range: {word_min}-{word_max} words
- {fmt_preset["structure"][-2] if len(fmt_preset["structure"]) > 1 else "Keep paragraphs short"}
- {"Expect lower mobile engagement due to length" if word_max > 350 else "Maximize mobile readability with short paragraphs"}
"""
        
        # Extract persona context for CTA personalization
        cta_style = user_persona.get("writing", {}).get("cta_style", "question")
        
        scorer_feedback_block = ""
        if score_feedback:
            weakest = ", ".join(score_feedback.get("weakest_dimensions", [])[:4])
            suggestions = "\n".join([f"- {s}" for s in score_feedback.get("improvement_suggestions", [])[:6]])
            scorer_feedback_block = f"""

    ### SCORER FEEDBACK TO FIX (MANDATORY)
    Weakest dimensions: {weakest or 'N/A'}
    {suggestions or '- Improve specificity and save-worthy value'}
    """

        prompt = f"""{MASTER_PROMPT}

### TASK: Optimize this LinkedIn post — you are the final editor before publishing

TONE: {tone}
AUDIENCE: {audience}
CTA STYLE PREFERENCE: {cta_style.title()}
{format_guidance}

### CURRENT DRAFT:
HOOK: {original_hook}

BODY:
{original_post}

CTA: {original_cta}

### YOUR EDITING CHECKLIST (apply each ruthlessly):

1. **HOOK AUDIT**: Does line 1 work in the LinkedIn preview (~210 chars)? Would YOU stop scrolling? If not, sharpen it.

2. **FILLER ELIMINATION**: Read every sentence. If removing it doesn't lose meaning → cut it. Target words: "actually", "really", "basically", "just", "very", "In order to".

3. **SPECIFICITY INJECTION**: Replace vague claims with concrete ones.
   BAD: "I've seen many companies struggle with this"
   GOOD: "Most major deployments in this space fail for a single reason: unmanaged dependencies"

4. **RHYTHM CHECK**: Read it aloud mentally. Alternate between:
   - Short punch (3-7 words)
   - Medium explanation (10-20 words)
   Break any sentence longer than 25 words into two.

5. **CTA UPGRADE**: The call-to-action must be an EITHER/OR or FILL-IN-THE-BLANK that people can answer in one sentence.
   BAD: "What do you think?"
   GOOD: "What's the one tool you'd refuse to give up, even if your company switched stacks?"

6. **MOBILE FORMAT**: Every paragraph ≤ 3 lines on mobile (~45 chars/line). Add line breaks if needed.

7. **COMMENT BAIT**: Ensure at least ONE statement that 30% of readers will disagree with. Disagreement = comments = reach.

8. **DEPTH + LENGTH**: Final output must be 180-260 words and include:
    - one concrete stat/company/tool
    - one emotional sentence
    - one practical 3-point takeaway

{scorer_feedback_block}

{emoji_instruction}

### OUTPUT FORMAT (valid JSON only):
{{
  "hook": "optimized hook",
  "post": "full optimized post with \\n line breaks",
  "cta": "optimized CTA",
  "hashtags": {json.dumps(generated_post.get("hashtags", []))},
  "viral_score_prediction": {generated_post.get("viral_score_prediction", 5.0)},
  "reasoning": "What exactly did you change and why? Be specific: 'Shortened hook from 18 to 9 words. Replaced generic CTA with either/or format. Cut 2 filler sentences.'"
}}

CRITICAL: Keep the author's core message and voice. You are editing, not rewriting from scratch. If the draft is already strong, make minimal changes and explain why."""

        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_OPTIMIZER(),
                options={"temperature": 0.5, "num_ctx": 8192},
            )
            track_llm_call("engagement_optimizer", response, model=MODEL_OPTIMIZER(), purpose="Optimize for engagement")

            optimized = _parse_json_from_llm(response)

            if not optimized.get("post"):
                # Optimization failed, keep original
                optimized = generated_post.copy()
                optimized["reasoning"] = "Optimization returned empty — kept original"

            # Preserve hashtags if optimizer dropped them
            if not optimized.get("hashtags"):
                optimized["hashtags"] = generated_post.get("hashtags", [])

        except Exception as e:
            log_error("engagement_optimizer", f"Optimization failed: {e}")
            optimized = generated_post.copy()
            optimized["reasoning"] = f"Optimization failed ({e}) — kept original"

        # Final safety net for short or generic local outputs
        if _word_count(optimized.get("post", "")) < 170 or _is_generic_cta(optimized.get("cta", "")):
            optimized["reasoning"] = (
                (optimized.get("reasoning", "") + "\n\n")
                + "Post may be too short or CTA too generic after optimization; scorer will request self-correction."
            ).strip()

        log_state_update("engagement_optimizer", "optimized_post", "post optimized")
        return {"optimized_post": optimized}


# ==========================================
# NODE 8: VIRAL SCORER (10-DIMENSION RUBRIC)
# ==========================================
def viral_scorer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Independently score the post's viral potential using a 10-dimension rubric.
    
    Each dimension scored 0-1 (total 0-10).
    Includes anti-anchoring instructions to prevent LLMs defaulting to middle scores.
    If score < 6.0, generates specific improvement suggestions for self-correction.
    """
    with NodeTimer("viral_scorer"):
        optimized_post = state.get("optimized_post", {})
        topic = state.get("topic", "")
        trends = state.get("trends", "")
        viral_examples = state.get("viral_examples", [])
        verified_claims = state.get("verified_claims", [])

        post_text = optimized_post.get("post", "")
        hook_text = optimized_post.get("hook", "")
        cta_text = optimized_post.get("cta", "")

        if _is_low_cost_mode():
            # Heuristic scoring with more variance
            score = 0.0
            words = post_text.split()
            lines = post_text.split("\n")

            # Hook present and punchy (< 15 words in first line)
            first_line_words = lines[0].split() if lines else []
            if hook_text and len(first_line_words) <= 15:
                score += 0.8
            elif hook_text:
                score += 0.4

            # Length sweet spot (150-280 words)
            wc = len(words)
            if 150 <= wc <= 280:
                score += 0.9
            elif 100 <= wc <= 350:
                score += 0.5
            else:
                score += 0.2

            # Has specific numbers/data
            import re as _re
            if _re.search(r'\d+%|\$\d|\d{2,}', post_text):
                score += 0.8
            else:
                score += 0.2

            # Paragraph rhythm (short paragraphs)
            paragraphs = [p for p in post_text.split("\n\n") if p.strip()]
            avg_para_len = sum(len(p.split()) for p in paragraphs) / max(len(paragraphs), 1)
            if avg_para_len <= 30:
                score += 0.7
            else:
                score += 0.3

            # CTA present and specific
            if cta_text and "?" in cta_text:
                score += 0.7
            elif cta_text:
                score += 0.3
            else:
                score += 0.1

            # Hashtags reasonable (2-3)
            ht = optimized_post.get("hashtags", [])
            if 2 <= len(ht) <= 3:
                score += 0.6
            else:
                score += 0.3

            # No filler phrases
            filler = ["in today's", "game-changer", "let's dive in", "here's the thing"]
            if not any(f in post_text.lower() for f in filler):
                score += 0.7
            else:
                score += 0.1

            # First-person voice
            if any(w in post_text.lower().split() for w in ["i", "i've", "my", "i'm", "we"]):
                score += 0.6
            else:
                score += 0.2

            # Trend relevance (basic keyword check)
            topic_words = set(topic.lower().split())
            if any(tw in post_text.lower() for tw in topic_words if len(tw) > 3):
                score += 0.5
            else:
                score += 0.2

            # Controversy/opinion signal
            opinion_signals = ["wrong", "stop", "never", "most people", "unpopular", "nobody talks"]
            if any(s in post_text.lower() for s in opinion_signals):
                score += 0.7
            else:
                score += 0.3

            # Realism score (source-backed and non-hype)
            verified_fact_count = len(verified_claims)
            if verified_fact_count >= 3:
                score += 0.8
            elif verified_fact_count >= 1:
                score += 0.5
            else:
                score += 0.2

            # Hyperbolic hook penalty (credibility)
            score -= round(_hyperbole_score(hook_text) * 0.3, 2)

            score = round(max(0.0, min(10.0, score)), 1)

            optimized = optimized_post.copy()
            optimized["viral_score_prediction"] = score
            optimized["reasoning"] = f"Heuristic score: {score}/10 (low-cost mode)"
            optimized.setdefault("score_breakdown", {})
            optimized["score_breakdown"]["realism_score"] = _compute_realism_components(verified_claims, hook_text).get("realism_score", 0.3)

            log_state_update("viral_scorer", "viral_score", f"{score}/10 (low-cost heuristic)")
            return {
                "optimized_post": optimized,
                "viral_score": score,
                "realism_score": optimized["score_breakdown"]["realism_score"],
            }

        # Compare with past high-performers — strict distance
        similarity_context = ""
        try:
            post_embedding = embed_text(post_text, is_query=True)
            similar = search_similar_posts(
                post_embedding,
                limit=3,
                max_distance=SIMILAR_MAX_DISTANCE,
                min_score=MIN_RETRIEVAL_SCORE,
            )
            for s in similar:
                similarity_context += f"- Past post (score: {s.get('viral_score', 'N/A')}, distance: {s.get('distance', 'N/A'):.3f}): {s.get('content', '')[:200]}\n"
        except Exception as e:
            log_error("viral_scorer", f"Similarity search failed: {e}")
            similarity_context = "No comparable past data available."

        prompt = f"""You are a LinkedIn content scoring algorithm. You must NOT default to middle scores.

### POST TO EVALUATE:
HOOK: {hook_text}

FULL POST:
{post_text}

CTA: {cta_text}

### 11-DIMENSION SCORING RUBRIC (each dimension: 0.0 to 1.0)

Score each dimension independently. Think step-by-step for each one.

1. **SCROLL-STOP POWER** (0.0-1.0): Will the first line make someone STOP scrolling?
   0.0 = Generic opener anyone could write
   0.5 = Interesting but not urgent
   1.0 = Physically impossible to not click "see more"

2. **SPECIFICITY** (0.0-1.0): Does the post contain concrete details?
   0.0 = All vague generalizations
   0.5 = Some specific claims but unverified
   1.0 = Named companies, exact numbers, real timelines

3. **EMOTIONAL RESONANCE** (0.0-1.0): Does it make the reader FEEL something?
   0.0 = Reads like a Wikipedia article
   0.5 = Mildly interesting
   1.0 = Reader feels frustration, excitement, vindication, or surprise

4. **STRUCTURAL FLOW** (0.0-1.0): Is it formatted for mobile LinkedIn?
   0.0 = Wall of text, long paragraphs
   0.5 = Some formatting but inconsistent
   1.0 = Perfect rhythm: short punches + breathing room

5. **VOICE AUTHENTICITY** (0.0-1.0): Does it sound like a REAL person?
   0.0 = Obviously AI-generated, corporate fluff
   0.5 = Decent but could be anyone
   1.0 = Distinctive voice, you'd recognize the author

6. **COMMENT MAGNETISM** (0.0-1.0): Will people NEED to respond?
   0.0 = Nothing to disagree with or add to
   0.5 = Some might comment
   1.0 = Contains a statement that splits the audience 50/50

7. **SAVE-WORTHY VALUE** (0.0-1.0): Would someone bookmark this?
   0.0 = No actionable insight
   0.5 = Interesting but not reference-worthy
   1.0 = Contains a framework, checklist, or insight worth revisiting

8. **TREND CURRENCY** (0.0-1.0): Is it timely and relevant?
   0.0 = Could have been written 5 years ago
   0.5 = Generally relevant
   1.0 = Tied to something happening RIGHT NOW

9. **CTA EFFECTIVENESS** (0.0-1.0): Will the closing drive action?
   0.0 = No CTA or generic "thoughts?"
   0.5 = Decent question but easy to ignore
   1.0 = Specific dilemma that people want to weigh in on

10. **SHAREABILITY** (0.0-1.0): Would someone repost this?
    0.0 = Too niche or too generic
    0.5 = Good content but no share trigger
    1.0 = Makes the sharer look smart/insightful

11. **REALISM_SCORE** (0.0-1.0): Is it believable and source-consistent?
    0.0 = Contains likely fabricated or unsupported claims
    0.5 = Mostly plausible but partially weakly supported
    1.0 = Claims are grounded, specific, and believable

### PAST COMPARISON:
{similarity_context if similarity_context else "No comparable past data."}

### ANTI-ANCHORING INSTRUCTIONS:
- Do NOT start from 5.0 and adjust. Score each dimension from scratch.
- The distribution should be VARIED: some dimensions will be 0.2, others 0.9.
- A truly average LinkedIn post scores 3.0-4.5 total. A good one scores 5.5-7.0. Viral = 8.0+.
- If all your subscores cluster around 0.5-0.7, you are being lazy. Spread them out.
- First compute raw_sum = SUM of all 11 dimensions (max 11.0)
- Then normalize to /10 using: viral_score = (raw_sum / 11) * 10

### OUTPUT (valid JSON only):
{{
  "scoring_reasoning": "2-3 sentences of chain-of-thought BEFORE scoring. What stands out? What's weak?",
  "breakdown": {{
    "scroll_stop_power": 0.7,
    "specificity": 0.3,
    "emotional_resonance": 0.8,
    "structural_flow": 0.6,
    "voice_authenticity": 0.5,
    "comment_magnetism": 0.9,
    "save_worthy_value": 0.4,
    "trend_currency": 0.7,
    "cta_effectiveness": 0.6,
        "shareability": 0.5,
        "realism_score": 0.7
  }},
  "viral_score": 6.0,
  "weakest_dimensions": ["specificity", "save_worthy_value"],
  "improvement_suggestions": [
    "Add a specific metric or company name to the main insight",
    "Include a mini-framework or 3-step takeaway to make it bookmark-worthy"
  ],
  "reasoning": "One paragraph: honest assessment of why this post will or won't go viral"
}}"""

        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_SCORER(),
                options={"temperature": 0.3, "num_ctx": 8192},
            )
            track_llm_call("viral_scorer", response, model=MODEL_SCORER(), purpose="Score viral potential")

            scored = _parse_json_from_llm(response)
            breakdown = scored.get("breakdown", {})
            score_reasoning = scored.get("reasoning", "")
            improvement_suggestions = list(scored.get("improvement_suggestions", []) or [])
            weakest = list(scored.get("weakest_dimensions", []) or [])

            # Calculate score from breakdown if dimensions are present (11 -> normalized /10)
            if breakdown and len(breakdown) >= 5:
                computed_score = sum(float(v) for v in breakdown.values())
                if len(breakdown) >= 11:
                    computed_score = (computed_score / len(breakdown)) * 10.0
                computed_score = round(max(0.0, min(10.0, computed_score)), 1)
                viral_score = computed_score
            else:
                viral_score = float(scored.get("viral_score", 5.0))
                viral_score = max(0.0, min(10.0, viral_score))

            if not isinstance(breakdown, dict):
                breakdown = {}

            realism_components = _compute_realism_components(verified_claims, hook_text)
            realism_adjusted = realism_components.get("realism_score", 0.0)
            breakdown["realism_score"] = realism_adjusted

            # Additional realism penalties affect overall viral score
            penalties = 0.0

            if not verified_claims:
                penalties += 0.7
                weakest.append("realism_score")
                improvement_suggestions.append("Add source-backed verified claims before making strong assertions.")

            if verified_claims and all(bool(c.get("blog_only", False)) for c in verified_claims):
                penalties += 0.2
                weakest.append("realism_score")
                improvement_suggestions.append("Add at least one independent non-blog source for key claims.")

            funding_claims = [c for c in verified_claims if str(c.get("type", "")).lower() == "funding"]
            if funding_claims and all(bool(c.get("wikipedia_only", False)) for c in funding_claims):
                penalties += 0.2
                weakest.append("realism_score")
                improvement_suggestions.append("Use primary or financial-news sources for funding claims, not Wikipedia-only links.")

            if _hyperbole_score(hook_text) >= 0.6:
                penalties += 0.2
                weakest.append("realism_score")
                improvement_suggestions.append("Reduce absolutist/hyperbolic hook language to protect credibility.")

            if any(bool(c.get("self_benchmark", False)) for c in verified_claims):
                penalties += 0.2
                weakest.append("realism_score")
                improvement_suggestions.append("Treat self-reported benchmark claims as provisional unless independently validated.")

            if realism_adjusted < 0.5:
                penalties += 0.4
                weakest.append("realism_score")
                improvement_suggestions.append("Increase claim plausibility and independent confirmation for stronger realism.")

            # Deterministic quality penalties to avoid inflated scores on short/generic posts
            # Format-aware word count validation
            wc = _word_count(post_text)
            post_format = state.get("post_format", "medium")
            format_preset = get_format_preset(post_format)
            min_wc, max_wc = format_preset["word_range"]
            
            if wc < min_wc:
                deficit = min_wc - wc
                penalties += 1.2
                improvement_suggestions.append(f"Expand the post to at least {min_wc} words (currently {wc}). Add richer context, examples, or proof.")
                weakest.append("structural_flow")
            elif wc > max_wc:
                excess = wc - max_wc
                penalties += 0.8
                improvement_suggestions.append(f"Trim the post to {max_wc} words max (currently {wc}). Remove redundant explanations or secondary arguments.")
                weakest.append("structural_flow")

            if not re.search(r"\d+%|\$\d|\b\d{2,}\b", post_text):
                penalties += 0.6
                improvement_suggestions.append("Add a concrete metric, number, or named example to increase specificity.")
                weakest.append("specificity")

            if _is_generic_cta(cta_text):
                penalties += 0.4
                improvement_suggestions.append("Replace generic CTA with either/or or fill-in-the-blank question.")
                weakest.append("cta_effectiveness")

            # Realism penalty: numbers present but weak verification coverage
            if re.search(r"\d+%|\$\d|\b\d{2,}\b", post_text) and len(verified_claims) == 0:
                penalties += 0.8
                improvement_suggestions.append("Remove unsupported numbers or add source-backed verified claims.")
                weakest.append("realism_score")
            elif len(verified_claims) < 2:
                penalties += 0.4
                improvement_suggestions.append("Anchor key statements to at least 2 verified claims.")
                weakest.append("realism_score")
            
            # Persona authenticity scoring (new dimension for personalization)
            user_persona = state.get("user_persona", {})
            job_role = user_persona.get("identity", {}).get("job_role", "")
            if job_role and job_role.lower() not in post_text.lower() and (job_role.lower() + "'s" not in post_text.lower()):
                # Post should reflect author's perspective somewhat
                if "we" in post_text.lower() or "i" in post_text.lower():
                    # Good - has first-person or inclusive language showing authentic voice
                    pass
                else:
                    # Missing personal perspective
                    penalties += 0.25
                    improvement_suggestions.append(f"Add personal perspective from a {job_role}'s viewpoint for authenticity.")



            if penalties > 0:
                viral_score = max(0.0, round(viral_score - penalties, 1))
                score_reasoning = (
                    (score_reasoning + " ").strip()
                    + f"Deterministic penalties applied: -{penalties:.1f} for length/specificity/CTA/realism guardrails."
                ).strip()

            # Deduplicate suggestions and weakest dimensions
            if improvement_suggestions:
                improvement_suggestions = list(dict.fromkeys([s for s in improvement_suggestions if s]))
            if weakest:
                weakest = list(dict.fromkeys([w for w in weakest if w]))

        except Exception as e:
            log_error("viral_scorer", f"Scoring failed: {e}")
            viral_score = 4.5  # Changed from 5.0 — slightly below average default
            score_reasoning = f"Scoring failed ({e}) — conservative default applied"
            breakdown = {}
            improvement_suggestions = []
            weakest = []

        # =============================
        # SELF-CORRECTION: If score < 6.0, feed improvements back to optimizer for a second pass
        # =============================
        optimized = state.get("optimized_post", {}).copy()

        if viral_score < 6.0 and improvement_suggestions and not _is_low_cost_mode():
            log_node("viral_scorer", "SELF-CORRECTION", f"Score {viral_score}/10 — running improvement pass")

            correction_prompt = f"""{MASTER_PROMPT}

### TASK: IMPROVE this LinkedIn post based on scorer feedback

The viral scorer rated this post {viral_score}/10. Here's what needs fixing:

WEAKEST AREAS: {', '.join(weakest)}

SPECIFIC FIXES NEEDED:
{chr(10).join(f'- {s}' for s in improvement_suggestions)}

### CURRENT POST:
{optimized.get('post', '')}

### CTA:
{optimized.get('cta', '')}

### RULES:
- Apply ONLY the suggested improvements
- Keep the same hook, flow, and voice
- Do NOT rewrite from scratch — make surgical edits
- Output the improved version

### OUTPUT (valid JSON only):
{{
  "post": "improved full post with \\n line breaks",
  "cta": "improved CTA if needed",
  "changes_made": ["list of specific changes you made"]
}}"""

            try:
                correction_response = chat(
                    messages=[{"role": "user", "content": correction_prompt}],
                    model=MODEL_OPTIMIZER(),
                    options={"temperature": 0.4, "num_ctx": 8192},
                )

                correction = _parse_json_from_llm(correction_response)
                if correction.get("post"):
                    optimized["post"] = correction["post"]
                    if correction.get("cta"):
                        optimized["cta"] = correction["cta"]
                    changes = correction.get("changes_made", [])
                    score_reasoning += f"\n\nSelf-correction applied: {', '.join(changes)}"
                    # Bump score slightly after corrections (conservative +0.5-1.0)
                    viral_score = min(10.0, viral_score + 0.7)
                    log_node("viral_scorer", "SELF-CORRECTION", f"Corrections applied. Adjusted score: {viral_score}/10")

            except Exception as e:
                log_error("viral_scorer", f"Self-correction failed: {e}")

        # Merge score into optimized post
        optimized["viral_score_prediction"] = viral_score
        if score_reasoning:
            optimized["reasoning"] = (
                optimized.get("reasoning", "") + f"\n\nViral Score: {viral_score}/10 — {score_reasoning}"
            )
        if breakdown:
            optimized["score_breakdown"] = breakdown

        score_feedback = {
            "weakest_dimensions": weakest,
            "improvement_suggestions": improvement_suggestions,
            "latest_score": viral_score,
            "realism_score": _safe_float((breakdown or {}).get("realism_score", 0.0), 0.0),
        }

        log_state_update("viral_scorer", "viral_score", f"{viral_score}/10")
        return {
            "optimized_post": optimized,
            "viral_score": viral_score,
            "realism_score": _safe_float((breakdown or {}).get("realism_score", 0.0), 0.0),
            "score_feedback": score_feedback,
        }


# ==========================================
# NODE 9: STORE POST IN PGVECTOR (QUALITY-GATED)
# ==========================================
def store_post_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Embed and store the final post in the linkedin_posts table.
    
    Quality rules:
    - Only store the embedding if viral_score >= MIN_STORE_SCORE (5.0)
    - Posts below threshold are saved without embedding (won't pollute retrieval)
    - This prevents low-quality posts from being retrieved as "style examples" later
    """
    with NodeTimer("store_post"):
        optimized_post = state.get("optimized_post", {})
        topic = state.get("topic", "")
        tone = state.get("tone", "professional")
        audience = state.get("audience", "tech professionals")
        viral_score = state.get("viral_score", 0.0)
        realism_score = state.get("realism_score", 0.0)
        angle_package = state.get("angle_package", {})

        post_content = optimized_post.get("post", "")
        hook = optimized_post.get("hook", "")
        cta = optimized_post.get("cta", "")
        hashtags = optimized_post.get("hashtags", [])
        reasoning = optimized_post.get("reasoning", "")

        post_id = None

        try:
            # QUALITY GATE: Only generate and store embedding for good posts
            embedding = None
            if viral_score >= MIN_STORE_SCORE:
                embedding = embed_text(post_content)
                log_node("store_post", "QUALITY GATE", f"Score {viral_score} >= {MIN_STORE_SCORE} — embedding stored for future retrieval")
            else:
                log_node("store_post", "QUALITY GATE", f"Score {viral_score} < {MIN_STORE_SCORE} — saved WITHOUT embedding (won't pollute retrieval)")

            # Insert into database (with or without embedding)
            post_id = insert_post(
                content=post_content,
                hook=hook,
                cta=cta,
                hashtags=hashtags,
                embedding=embedding,
                viral_score=viral_score,
                tone=tone,
                audience=audience,
                topic=topic,
                reasoning=reasoning,
                status="draft",
                score_breakdown=optimized_post.get("score_breakdown", {}),
                realism_score=realism_score,
            )

            if post_id and angle_package:
                insert_angle_result(
                    post_id=post_id,
                    topic=topic,
                    angle_type=angle_package.get("angle_type", ""),
                    best_angle=angle_package.get("best_angle", ""),
                    risk_level=angle_package.get("risk_level", "med"),
                    viral_score=viral_score,
                    realism_score=realism_score,
                    supporting_facts=angle_package.get("supporting_facts", []),
                )
        except Exception as e:
            log_error("store_post", f"Storage failed: {e}")

        # Assemble final_post
        final_post = {
            "post_id": post_id or "",
            "hook": hook,
            "post": post_content,
            "cta": cta,
            "hashtags": hashtags,
            "viral_score_prediction": viral_score,
            "reasoning": reasoning,
            "tone": tone,
            "audience": audience,
            "topic": topic,
            "status": "draft",
            "score_breakdown": optimized_post.get("score_breakdown", {}),
            "realism_score": realism_score,
        }

        if not post_id:
            return {
                "final_post": final_post,
                "post_id": "",
                "error": "Failed to save generated post to database",
            }

        log_state_update("store_post", "final_post+post_id", f"stored as {post_id}")
        
        # Send pipeline_complete event for draft mode (before human_approval interrupt)
        log_agent_end(
            post_id,
            viral_score,
            final_post=final_post,
            iteration_count=state.get("iteration_count", 0),
            hooks=state.get("hooks", []),
            realism_score=realism_score
        )
        
        return {"final_post": final_post, "post_id": post_id or ""}


# ==========================================
# NODE 10: HUMAN APPROVAL
# ==========================================
def human_approval_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Placeholder node for human-in-the-loop approval.
    The actual interrupt happens BEFORE this node via interrupt_before.
    """
    with NodeTimer("human_approval"):
        current_status = state.get("approval_status", "")
        if current_status in ("approved", "regenerate", "rejected"):
            log_node("human_approval", "NODE EXECUTION", f"preserving approval_status={current_status}")
            return {"approval_status": current_status}

        log_node("human_approval", "NODE EXECUTION", "awaiting human approval")
        return {"approval_status": "awaiting"}


# ==========================================
# NODE 11: LINKEDIN PUBLISH
# ==========================================
def linkedin_publish_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Publish the approved post to LinkedIn."""
    with NodeTimer("linkedin_publish"):
        log_node("linkedin_publish", "NODE EXECUTION", "linkedin_publish_node invoked")

        final_post = state.get("final_post", {})
        auto_publish = state.get("auto_publish", False)
        approval_status = state.get("approval_status", "")
        post_id = state.get("post_id", "")

        log_node("linkedin_publish", "DEBUG", f"approval_status={approval_status}, auto_publish={auto_publish}, post_id={post_id}")

        # Only publish if approved or auto-publish enabled
        if approval_status not in ("approved",) and not auto_publish:
            log_node("linkedin_publish", "NODE EXECUTION", f"skipped — status: {approval_status}")
            return {"publish_url": ""}

        post_text = final_post.get("post", "")
        hashtags = final_post.get("hashtags", [])

        # Append hashtags to post
        if hashtags:
            hashtag_line = " ".join([f"#{h.lstrip('#')}" for h in hashtags])
            full_text = f"{post_text}\n\n{hashtag_line}"
        else:
            full_text = post_text

        # Check for access token
        token = get_access_token()
        log_node("linkedin_publish", "DEBUG", f"access_token present: {bool(token)}")

        if not token:
            log_error("linkedin_publish", "No LinkedIn access token. Complete OAuth2 flow first.")
            # Update post status to approved (but not published)
            if post_id:
                update_post_status(post_id, "approved")
            return {
                "publish_url": "",
                "approval_status": "approved_not_published",
            }

        # Publish
        log_node("linkedin_publish", "DEBUG", f"calling publish_text_post with {len(full_text)} chars")

        try:
            result = publish_text_post(text=full_text, access_token=token)

            log_node("linkedin_publish", "DEBUG", f"publish_text_post result: {result}")

            if "error" in result:
                log_error("linkedin_publish", f"Publish failed: {result['error']}")
                if post_id:
                    update_post_status(post_id, "approved")
                return {
                    "publish_url": "",
                    "approval_status": "publish_failed",
                    "error": result["error"],
                }

            publish_url = result.get("url", "")
            if post_id:
                update_post_status(post_id, "published", publish_url)

                # Best-effort engagement snapshot for learning loop
                engagement = fetch_post_engagement(post_url=publish_url)
                if "error" not in engagement:
                    insert_post_engagement(
                        post_id=post_id,
                        publish_url=publish_url,
                        linkedin_post_urn=engagement.get("post_urn", ""),
                        impressions=engagement.get("impressions", 0),
                        reactions=engagement.get("reactions", 0),
                        comments=engagement.get("comments", 0),
                        reposts=engagement.get("reposts", 0),
                        payload=engagement.get("payload", {}),
                    )

            log_agent_end(
                post_id, 
                state.get("viral_score", 0),
                final_post=final_post,
                iteration_count=state.get("iteration_count", 0),
                hooks=state.get("hooks", []),
                realism_score=state.get("realism_score", 0.0)
            )
            log_state_update("linkedin_publish", "publish_url", publish_url)

            return {
                "publish_url": publish_url,
                "approval_status": "published",
            }

        except Exception as e:
            log_error("linkedin_publish", f"Publish exception: {e}")
            if post_id:
                update_post_status(post_id, "approved")
            return {
                "publish_url": "",
                "approval_status": "publish_failed",
                "error": str(e),
            }
