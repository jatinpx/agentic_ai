from services.llm_client import chat
import re
from sentence_transformers import CrossEncoder

# Fast reranker (runs well on CPU)
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def pick_memory_for_role(query: str, memories: list[str], role: str, k: int = 2):
    """
    2-stage memory selection:
    1. Semantic rerank (MiniLM cross-encoder)
    2. Logical selection via Llama
    Optimized for local 6GB VRAM (RTX 3060)
    """

    # --- SAFETY CLEAN ---
    safe_memories = [
        str(m).strip()
        for m in memories
        if m and isinstance(m, (str, int, float))
    ]

    if not safe_memories:
        print(f"⚠️ [MEMORY] No valid memories for role={role}")
        return []

    # =============================
    # STAGE 1: SEMANTIC RERANK
    # =============================
    try:
        pairs = [[query, m] for m in safe_memories]
        scores = reranker.predict(pairs)

        scored = sorted(
            zip(safe_memories, scores),
            key=lambda x: x[1],
            reverse=True
        )

        top_candidates = [m[0] for m in scored[:6]]

    except Exception as e:
        print(f"⚠️ Reranker failed: {e}")
        top_candidates = safe_memories[:6]

    if not top_candidates:
        return []

    # =============================
    # STAGE 2: ROLE LOGIC (LLM)
    # =============================
    role_intents = {
        "planner": "strategic patterns, workflows, and high-level plans",
        "executor": "technical steps, tools, code, outputs, and factual knowledge",
        "critic": "mistakes, failures, hallucinations, and corrections"
    }
    intent = role_intents.get(role.lower(), "relevance to the task")

    mem_blob = "\n".join(
        [f"{i+1}. {m[:350]}" for i, m in enumerate(top_candidates)]
    )

    prompt = f"""
You are the memory selection module inside an autonomous AI agent.

ROLE: {role.upper()}
TASK: {query}
FOCUS: {intent}

CANDIDATE MEMORIES:
{mem_blob}

STRICT RULES:
- Select up to {k} best memories.
- If none useful → return NONE
- Return ONLY numbers separated by comma.
- No explanation.
- No text.
- Example: 1,3
"""

    # =============================
    # LLM CALL (optimized for 3060)
    # =============================
    try:
        res = chat(
            messages=[{"role": "user", "content": prompt}],
            model="llama3.1:8b-instruct-q4_K_M",
            options={
                "temperature": 0,
                "top_p": 0.85,
                "top_k": 30,
                "repeat_penalty": 1.05,
                "num_predict": 12,
                "num_ctx": 4096,
                "num_thread": 8,      # adjust to CPU cores
            }
        )
    except Exception as e:
        print(f"⚠️ LLM call failed: {e}")
        return top_candidates[:k]

    if not res:
        return top_candidates[:k]

    res = res.strip()

    # =============================
    # STAGE 3: SAFE PARSING
    # =============================
    if "NONE" in res.upper():
        return []

    found_ids = re.findall(r"\d+", res)

    if not found_ids:
        # fallback: return semantic top-k
        return top_candidates[:k]

    indices = []
    for i in found_ids:
        idx = int(i) - 1
        if 0 <= idx < len(top_candidates) and idx not in indices:
            indices.append(idx)

    final = [top_candidates[i] for i in indices]

    if not final:
        return top_candidates[:k]

    return final[:k]
