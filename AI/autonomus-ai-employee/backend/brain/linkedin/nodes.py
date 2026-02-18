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
import time
from typing import Dict, Any

from dotenv import load_dotenv

load_dotenv()

from services.llm_client import chat
from services.memory_service import recall_memory
from services.memory_picker import pick_memory_for_role
from embeddings.embedder import embed_text
from tools.tavily_web_search import tavily_search
from db.linkedin_repo import (
    insert_post,
    search_similar_posts,
    search_viral_templates,
    get_top_posts,
    update_post_status,
)
from services.linkedin_api import publish_text_post, get_access_token
from brain.linkedin.models import PostInput
from brain.linkedin.logging_utils import (
    log_node, log_agent_start, log_agent_end,
    log_state_update, log_token_usage, log_error, NodeTimer,
)


# ==========================================
# PER-NODE MODEL CONFIGURATION (from env)
# ==========================================
def _get_model(env_key: str, fallback: str = "qwen2.5:7b-instruct") -> str:
    return os.getenv(env_key, fallback)

MODEL_INPUT       = lambda: _get_model("LINKEDIN_MODEL_INPUT")
MODEL_STYLE_FETCH = lambda: _get_model("LINKEDIN_MODEL_STYLE_FETCH")
MODEL_VIRAL_FETCH = lambda: _get_model("LINKEDIN_MODEL_VIRAL_FETCH")
MODEL_TREND       = lambda: _get_model("LINKEDIN_MODEL_TREND")
MODEL_HOOK_GEN    = lambda: _get_model("LINKEDIN_MODEL_HOOK_GEN")
MODEL_WRITER      = lambda: _get_model("LINKEDIN_MODEL_WRITER")
MODEL_OPTIMIZER   = lambda: _get_model("LINKEDIN_MODEL_OPTIMIZER")
MODEL_SCORER      = lambda: _get_model("LINKEDIN_MODEL_SCORER")


# ==========================================
# MASTER SYSTEM PROMPT
# ==========================================
MASTER_PROMPT = """You are an elite LinkedIn content strategist and viral post generator.

Your job is to create high-quality LinkedIn posts that maximize:
- engagement
- authority
- clarity
- authenticity
- saves and comments

You DO NOT write generic AI content.
You write like a real human expert with strong opinions and insights.

POST GOALS:
- Hook reader in first 2 lines
- Provide value, insight, or story
- Sound human, not robotic
- Be concise and readable
- Use line breaks for LinkedIn formatting
- End with engagement CTA (question/debate/insight)

STYLE RULES:
- No cringe AI tone
- No emojis unless requested
- Avoid corporate buzzwords
- Use strong hooks
- Use curiosity + authority
- Write like an experienced tech professional
- If controversial tone requested → be bold but intelligent

CONTENT INTELLIGENCE:
When writing posts:
- Analyze past viral posts from memory
- Reuse high-performing hook patterns
- Maintain user's writing style
- Optimize for readability & saves
- Prefer clarity over complexity"""


def _clean_think_tags(text: str) -> str:
    """Remove <think>...</think> tags from LLM output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def _parse_json_from_llm(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    cleaned = _clean_think_tags(text)
    
    # Try to extract JSON from markdown code block
    json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL)
    if json_match:
        cleaned = json_match.group(1)
    
    # Try direct JSON parse
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    
    # Try to find a JSON object in the text
    brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", cleaned, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group())
        except json.JSONDecodeError:
            pass
    
    return {}


# ==========================================
# NODE 1: INPUT VALIDATION
# ==========================================
def input_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and unpack user input into state fields."""
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

        log_agent_start(validated.topic)
        log_state_update("input_node", "topic+tone+audience+goal", validated.topic)

        return {
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
    """Fetch user's previous posts from pgvector to match writing style."""
    with NodeTimer("style_memory_fetch"):
        topic = state.get("topic", "")
        
        style_examples = []

        # 1. Recall from general agent memory (past posts stored there)
        try:
            raw_memories = recall_memory(topic, limit=10)
            memory_strings = []
            for item in raw_memories:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    content = str(item[0]).strip()
                    distance = float(item[1]) if item[1] else 1.0
                    if content and distance <= 0.5:
                        memory_strings.append(content)
                elif isinstance(item, str):
                    memory_strings.append(item.strip())

            # Use memory picker to select style-relevant memories
            if memory_strings:
                picked = pick_memory_for_role(
                    query=f"LinkedIn post style for: {topic}",
                    memories=memory_strings,
                    role="writer",
                    k=3,
                )
                style_examples.extend(picked)
        except Exception as e:
            log_error("style_memory_fetch", f"Memory recall failed: {e}")

        # 2. Also search past LinkedIn posts by similarity
        try:
            query_embedding = embed_text(topic, is_query=True)
            similar_posts = search_similar_posts(query_embedding, limit=5)
            for post in similar_posts:
                if post.get("content") and post["distance"] <= 0.6:
                    style_examples.append(post["content"][:500])
        except Exception as e:
            log_error("style_memory_fetch", f"Post search failed: {e}")

        log_state_update("style_memory_fetch", "style_examples", f"{len(style_examples)} examples found")
        return {"style_examples": style_examples}


# ==========================================
# NODE 3: VIRAL POSTS FETCH
# ==========================================
def viral_posts_fetch_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch viral post templates and high-performing past posts."""
    with NodeTimer("viral_posts_fetch"):
        topic = state.get("topic", "")
        viral_examples = []

        try:
            query_embedding = embed_text(topic, is_query=True)

            # 1. Search viral templates
            templates = search_viral_templates(query_embedding, limit=5)
            for t in templates:
                if t.get("content"):
                    viral_examples.append({
                        "content": t["content"][:500],
                        "hook_pattern": t.get("hook_pattern", ""),
                        "category": t.get("category", ""),
                        "score": t.get("engagement_score", 0),
                    })

            # 2. Search high-scoring past posts
            top_posts = get_top_posts(limit=5, min_score=7.0)
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

        log_state_update("viral_posts_fetch", "viral_examples", f"{len(viral_examples)} examples found")
        return {"viral_examples": viral_examples}


# ==========================================
# NODE 4: TREND RESEARCH
# ==========================================
def trend_research_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Research current trends related to the topic using Tavily."""
    with NodeTimer("trend_research"):
        topic = state.get("topic", "")
        trends = ""

        try:
            # Search for current trends
            current_month = time.strftime("%B %Y")

            trend_query = f"LinkedIn trending topics {topic} {current_month}"
            trend_results = tavily_search(trend_query, max_results=3)

            angle_query = f"{topic} controversial takes insights tech industry {current_month}"
            angle_results = tavily_search(angle_query, max_results=3)

            # Synthesize trends using LLM
            prompt = f"""Analyze these search results and extract:
1. Current trends related to "{topic}"
2. Relevant angles and perspectives
3. Controversial or bold takes that would perform well on LinkedIn

TREND SEARCH RESULTS:
{trend_results}

ANGLE SEARCH RESULTS:
{angle_results}

Return a concise summary with bullet points. Focus on actionable insights for writing a LinkedIn post.
Keep it under 300 words. No fluff."""

            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_TREND(),
                options={"temperature": 0.3, "num_ctx": 4096},
            )

            trends = _clean_think_tags(response)

        except Exception as e:
            log_error("trend_research", f"Trend research failed: {e}")
            trends = f"Could not fetch current trends. Topic: {topic}"

        log_state_update("trend_research", "trends", f"{len(trends)} chars")
        return {"trends": trends}


# ==========================================
# NODE 5: HOOK GENERATOR
# ==========================================
def hook_generator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate 5 hook types and select the best one."""
    with NodeTimer("hook_generator"):
        topic = state.get("topic", "")
        tone = state.get("tone", "professional")
        trends = state.get("trends", "")
        style_examples = state.get("style_examples", [])
        viral_examples = state.get("viral_examples", [])
        include_emojis = state.get("include_emojis", False)

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

        prompt = f"""{MASTER_PROMPT}

### TASK: Generate 5 LinkedIn post hooks

TOPIC: {topic}
TONE: {tone}
{emoji_instruction}

### CURRENT TRENDS:
{trends[:500]}

### STYLE REFERENCES (user's past posts):
{style_ctx}

### VIRAL REFERENCES (high-performing posts):
{viral_ctx}

### INSTRUCTIONS:
Generate exactly 5 hooks, one for each type:
1. CURIOSITY — Makes reader stop scrolling to find out more
2. AUTHORITY — Establishes instant credibility
3. CONTRARIAN — Challenges conventional wisdom
4. STORYTELLING — Opens with a compelling mini-narrative
5. DEBATE — Sparks discussion and comments

For each hook, provide:
- type: the hook type
- text: the actual hook (2-3 lines max, LinkedIn formatted)
- strength_score: 1-10 rating

Then select the BEST hook.

Return ONLY valid JSON:
{{
  "hooks": [
    {{"type": "curiosity", "text": "...", "strength_score": 8}},
    {{"type": "authority", "text": "...", "strength_score": 7}},
    {{"type": "contrarian", "text": "...", "strength_score": 9}},
    {{"type": "storytelling", "text": "...", "strength_score": 6}},
    {{"type": "debate", "text": "...", "strength_score": 7}}
  ],
  "best_hook_index": 2,
  "reason": "why this hook is best"
}}"""

        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_HOOK_GEN(),
                options={"temperature": 0.7, "num_ctx": 4096},
            )

            parsed = _parse_json_from_llm(response)
            hooks = parsed.get("hooks", [])
            best_idx = parsed.get("best_hook_index", 0)

            if hooks and 0 <= best_idx < len(hooks):
                selected_hook = hooks[best_idx].get("text", "")
            elif hooks:
                # Fallback: pick highest score
                hooks_sorted = sorted(hooks, key=lambda h: h.get("strength_score", 0), reverse=True)
                selected_hook = hooks_sorted[0].get("text", "")
            else:
                selected_hook = f"Here's something most people get wrong about {topic}."
                hooks = [{"type": "fallback", "text": selected_hook, "strength_score": 5}]

        except Exception as e:
            log_error("hook_generator", f"Hook generation failed: {e}")
            selected_hook = f"Here's something most people get wrong about {topic}."
            hooks = [{"type": "fallback", "text": selected_hook, "strength_score": 5}]

        log_state_update("hook_generator", "hooks+selected_hook", f"{len(hooks)} hooks, best: {selected_hook[:50]}...")
        return {"hooks": hooks, "selected_hook": selected_hook}


# ==========================================
# NODE 6: POST WRITER (MAIN BRAIN)
# ==========================================
def post_writer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Write the full LinkedIn post using all gathered context."""
    with NodeTimer("post_writer"):
        topic = state.get("topic", "")
        tone = state.get("tone", "professional")
        audience = state.get("audience", "tech professionals")
        goal = state.get("goal", "engagement")
        include_emojis = state.get("include_emojis", False)
        selected_hook = state.get("selected_hook", "")
        trends = state.get("trends", "")
        style_examples = state.get("style_examples", [])
        viral_examples = state.get("viral_examples", [])
        hooks = state.get("hooks", [])

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

        prompt = f"""{MASTER_PROMPT}

### TASK: Write a complete LinkedIn post

TOPIC: {topic}
TONE: {tone}
AUDIENCE: {audience}
GOAL: {goal}
{emoji_instruction}

### SELECTED HOOK (use this as the opening):
{selected_hook}

### CURRENT TRENDS:
{trends[:500]}

### STYLE REFERENCES (match this writing style):
{style_ctx}

### VIRAL REFERENCES (learn from these):
{viral_ctx}

### ALL GENERATED HOOKS (for reference):
{hooks_ctx}

### OUTPUT FORMAT:
Return ONLY valid JSON. No other text.

{{
  "hook": "the opening 1-2 lines that grab attention",
  "post": "the FULL post body including hook, main content, and CTA. Use \\n for line breaks. Format for LinkedIn (short paragraphs, line breaks between ideas).",
  "cta": "the closing call-to-action question or statement",
  "hashtags": ["hashtag1", "hashtag2", "hashtag3"],
  "viral_score_prediction": 7.5,
  "reasoning": "brief explanation of why this post will perform well"
}}

CRITICAL RULES:
- The post MUST start with the selected hook
- Use short paragraphs (1-3 sentences each)
- Add blank lines between paragraphs for LinkedIn formatting
- The CTA should invite comments or saves
- Hashtags should be 3-5, relevant, and not overly generic
- viral_score_prediction should be honest (not always high)
- reasoning should reference specific elements that drive engagement"""

        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_WRITER(),
                options={"temperature": 0.7, "num_ctx": 8192},
            )

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
    """Optimize the post for engagement: readability, CTA, spacing, punchlines."""
    with NodeTimer("engagement_optimizer"):
        generated_post = state.get("generated_post", {})
        tone = state.get("tone", "professional")
        audience = state.get("audience", "tech professionals")
        include_emojis = state.get("include_emojis", False)

        original_post = generated_post.get("post", "")
        original_cta = generated_post.get("cta", "")
        original_hook = generated_post.get("hook", "")

        emoji_instruction = "Add 1-2 relevant emojis per section if they add value." if include_emojis else "Remove ALL emojis if any exist."

        prompt = f"""{MASTER_PROMPT}

### TASK: Optimize this LinkedIn post for maximum engagement

TONE: {tone}
AUDIENCE: {audience}

### CURRENT POST:
HOOK: {original_hook}

POST BODY:
{original_post}

CTA: {original_cta}

### OPTIMIZATION AREAS:
1. READABILITY — Ensure short paragraphs, proper line breaks, scannable format
2. HOOK STRENGTH — Make the first 2 lines even more compelling
3. CTA POWER — Make the call-to-action irresistible (provoke comments/saves)
4. PUNCHLINES — Add 1-2 punchy one-liners that are quotable/saveable
5. COMMENT BAIT — Ensure at least one statement that compels people to respond
6. SPACING — Optimize for mobile LinkedIn reading (short lines, breaks)
7. FLOW — Ensure smooth transitions between ideas
{emoji_instruction}

### OUTPUT FORMAT:
Return ONLY valid JSON with the optimized version:

{{
  "hook": "optimized hook",
  "post": "full optimized post with \\n line breaks",
  "cta": "optimized CTA",
  "hashtags": {json.dumps(generated_post.get("hashtags", []))},
  "viral_score_prediction": {generated_post.get("viral_score_prediction", 5.0)},
  "reasoning": "what was improved and why it will perform better"
}}

RULE: Keep the core message and voice intact. Only improve structure, impact, and engagement potential."""

        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_OPTIMIZER(),
                options={"temperature": 0.5, "num_ctx": 8192},
            )

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

        log_state_update("engagement_optimizer", "optimized_post", "post optimized")
        return {"optimized_post": optimized}


# ==========================================
# NODE 8: VIRAL SCORER
# ==========================================
def viral_scorer_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Independently score the post's viral potential (0-10)."""
    with NodeTimer("viral_scorer"):
        optimized_post = state.get("optimized_post", {})
        topic = state.get("topic", "")
        trends = state.get("trends", "")
        viral_examples = state.get("viral_examples", [])

        post_text = optimized_post.get("post", "")
        hook_text = optimized_post.get("hook", "")

        # Compare with past high-performers
        similarity_context = ""
        try:
            post_embedding = embed_text(post_text, is_query=True)
            similar = search_similar_posts(post_embedding, limit=3)
            for s in similar:
                similarity_context += f"- Similar post (score: {s.get('viral_score', 'N/A')}, distance: {s.get('distance', 'N/A'):.3f}): {s.get('content', '')[:200]}\n"
        except Exception as e:
            log_error("viral_scorer", f"Similarity search failed: {e}")
            similarity_context = "No past data available"

        prompt = f"""You are a LinkedIn viral content scoring algorithm.

Score this post from 0 to 10 based on these criteria:

### POST TO SCORE:
HOOK: {hook_text}

FULL POST:
{post_text}

### SCORING CRITERIA (each out of 2 points, total 10):
1. HOOK STRENGTH (0-2): Does the first line stop the scroll?
2. CLARITY (0-2): Is the message clear and easy to follow?
3. TREND RELEVANCE (0-2): Does it tap into current conversations?
4. ENGAGEMENT POTENTIAL (0-2): Will people comment, share, or save?
5. AUTHENTICITY (0-2): Does it sound human, opinionated, and real?

### CONTEXT:
Current trends: {trends[:300]}
Similar past posts: {similarity_context if similarity_context else "No past data"}

### OUTPUT FORMAT:
Return ONLY valid JSON:

{{
  "viral_score": 7.5,
  "breakdown": {{
    "hook_strength": 1.8,
    "clarity": 1.5,
    "trend_relevance": 1.2,
    "engagement_potential": 1.5,
    "authenticity": 1.5
  }},
  "reasoning": "brief explanation of the score"
}}

BE HONEST. Not every post is a 9/10. Average LinkedIn posts score 4-6."""

        try:
            response = chat(
                messages=[{"role": "user", "content": prompt}],
                model=MODEL_SCORER(),
                options={"temperature": 0.2, "num_ctx": 4096},
            )

            scored = _parse_json_from_llm(response)
            viral_score = float(scored.get("viral_score", 5.0))
            viral_score = max(0.0, min(10.0, viral_score))

            # Update reasoning in optimized post
            score_reasoning = scored.get("reasoning", "")
            breakdown = scored.get("breakdown", {})

        except Exception as e:
            log_error("viral_scorer", f"Scoring failed: {e}")
            viral_score = 5.0
            score_reasoning = f"Scoring failed ({e}) — default score applied"
            breakdown = {}

        # Merge score into optimized post
        optimized = state.get("optimized_post", {}).copy()
        optimized["viral_score_prediction"] = viral_score
        if score_reasoning:
            optimized["reasoning"] = (
                optimized.get("reasoning", "") + f"\n\nViral Score: {viral_score}/10 — {score_reasoning}"
            )
        if breakdown:
            optimized["score_breakdown"] = breakdown

        log_state_update("viral_scorer", "viral_score", f"{viral_score}/10")
        return {"optimized_post": optimized, "viral_score": viral_score}


# ==========================================
# NODE 9: STORE POST IN PGVECTOR
# ==========================================
def store_post_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Embed and store the final post in the linkedin_posts table."""
    with NodeTimer("store_post"):
        optimized_post = state.get("optimized_post", {})
        topic = state.get("topic", "")
        tone = state.get("tone", "professional")
        audience = state.get("audience", "tech professionals")
        viral_score = state.get("viral_score", 0.0)

        post_content = optimized_post.get("post", "")
        hook = optimized_post.get("hook", "")
        cta = optimized_post.get("cta", "")
        hashtags = optimized_post.get("hashtags", [])
        reasoning = optimized_post.get("reasoning", "")

        post_id = None

        try:
            # Generate embedding for the post
            embedding = embed_text(post_content)

            # Insert into database
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
        }

        log_state_update("store_post", "final_post+post_id", f"stored as {post_id}")
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
        log_node("human_approval", "NODE EXECUTION", "awaiting human approval")
        return {"approval_status": "awaiting"}


# ==========================================
# NODE 11: LINKEDIN PUBLISH
# ==========================================
def linkedin_publish_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Publish the approved post to LinkedIn."""
    with NodeTimer("linkedin_publish"):
        final_post = state.get("final_post", {})
        auto_publish = state.get("auto_publish", False)
        approval_status = state.get("approval_status", "")
        post_id = state.get("post_id", "")

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
        try:
            result = publish_text_post(text=full_text, access_token=token)

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

            log_agent_end(post_id, state.get("viral_score", 0))
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
