from services.llm_client import chat
import re
from sentence_transformers import CrossEncoder

# Fast reranker (runs well on CPU)
reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


# def pick_memory_for_role(query: str, memories: list[str], role: str, k: int = 2):
#     """
#     2-stage memory selection:
#     1. Semantic rerank (MiniLM cross-encoder)
#     2. Logical selection via Llama
#     Optimized for local 6GB VRAM (RTX 3060)
#     """

#     # --- SAFETY CLEAN ---
#     safe_memories = [
#         str(m).strip()
#         for m in memories
#         if m and isinstance(m, (str, int, float))
#     ]

#     if not safe_memories:
#         print(f"⚠️ [MEMORY] No valid memories for role={role}")
#         return []

#     # =============================
#     # STAGE 1: SEMANTIC RERANK
#     # =============================
#     try:
#         pairs = [[query, m] for m in safe_memories]
#         scores = reranker.predict(pairs)

#         scored = sorted(
#             zip(safe_memories, scores),
#             key=lambda x: x[1],
#             reverse=True
#         )

#         top_candidates = [m[0] for m in scored[:6]]

#     except Exception as e:
#         print(f"⚠️ Reranker failed: {e}")
#         top_candidates = safe_memories[:6]

#     if not top_candidates:
#         return []

#     # =============================
#     # STAGE 2: ROLE LOGIC (LLM)
#     # =============================
#     role_intents = {
#         "planner": "strategic patterns, workflows, and high-level plans",
#         "executor": "technical steps, tools, code, outputs, and factual knowledge",
#         "critic": "mistakes, failures, hallucinations, and corrections"
#     }
#     intent = role_intents.get(role.lower(), "relevance to the task")

#     mem_blob = "\n".join(
#         [f"{i+1}. {m[:350]}" for i, m in enumerate(top_candidates)]
#     )

#     prompt = f"""
# You are the memory selection module inside an autonomous AI agent.

# ROLE: {role.upper()}
# TASK: {query}
# FOCUS: {intent}

# CANDIDATE MEMORIES:
# {mem_blob}

# STRICT RULES:
# - Select up to {k} best memories.
# - If none useful → return NONE
# - Return ONLY numbers separated by comma.
# - No explanation.
# - No text.
# - Example: 1,3
# """

#     # =============================
#     # LLM CALL (optimized for 3060)
#     # =============================
#     try:
#         res = chat(
#             messages=[{"role": "user", "content": prompt}],
#             model="llama3.1:8b-instruct-q4_K_M",
#             options={
#                 "temperature": 0,
#                 "top_p": 0.85,
#                 "top_k": 30,
#                 "repeat_penalty": 1.05,
#                 "num_predict": 12,
#                 "num_ctx": 4096,
#                 "num_thread": 8,      # adjust to CPU cores
#             }
#         )
#     except Exception as e:
#         print(f"⚠️ LLM call failed: {e}")
#         return top_candidates[:k]

#     if not res:
#         return top_candidates[:k]

#     res = res.strip()

#     # =============================
#     # STAGE 3: SAFE PARSING
#     # =============================
#     if "NONE" in res.upper():
#         return []

#     found_ids = re.findall(r"\d+", res)

#     if not found_ids:
#         # fallback: return semantic top-k
#         return top_candidates[:k]

#     indices = []
#     for i in found_ids:
#         idx = int(i) - 1
#         if 0 <= idx < len(top_candidates) and idx not in indices:
#             indices.append(idx)

#     final = [top_candidates[i] for i in indices]

#     if not final:
#         return top_candidates[:k]

#     return final[:k]

def pick_memory_for_role(query: str, memories: list[str], role: str, k: int = 2):
    # --- SAFETY CLEAN (Unchanged) ---
    safe_memories = [str(m).strip() for m in memories if m and isinstance(m, (str, int, float))]
    if not safe_memories: return []

    # =============================
    # STAGE 1: SEMANTIC RERANK
    # =============================
    try:
        # Optimization: Only rerank if we have more than k memories
        if len(safe_memories) <= k:
            return safe_memories
            
        pairs = [[query, m] for m in safe_memories]
        scores = reranker.predict(pairs)
        scored = sorted(zip(safe_memories, scores), key=lambda x: x[1], reverse=True)
        
        # We take top 8 instead of 6 to give the LLM more 'breath'
        top_candidates = [m[0] for m in scored[:8]]
    except Exception as e:
        print(f"⚠️ Reranker failed: {e}")
        top_candidates = safe_memories[:8]

    # =============================
    # STAGE 2: ROLE LOGIC (LLM)
    # =============================
    role_intents = {
        "planner": "strategic patterns, workflows, and high-level plans",
        "executor": "technical steps, tools, code, and factual results",
        "critic": "errors, failures, risks, and necessary corrections"
    }
    intent = role_intents.get(role.lower(), "relevance to the task")

    # Optimization: Use Markdown list for better LLM parsing
    mem_blob = ""
    for i, m in enumerate(top_candidates):
        # Truncate to 400 for slightly more context than 350
        mem_blob += f"ID [{i+1}]: {m[:400]}\n"

    # Improved Prompt: Directives are now at the bottom (closer to generation)
    prompt = f"""You are a Memory Selection specialist.
Goal: Pick memories for the {role.upper()} role focusing on: {intent}.
Task: {query}

MEMORIES TO EVALUATE:
{mem_blob}

STRICT OUTPUT RULE:
- Pick the top {k} IDs (e.g., 1, 4)
- If nothing fits, reply 'NONE'
- Output ONLY the numbers. No text.
IDs:"""

    try:
        res = chat(
            messages=[{"role": "user", "content": prompt}],
            # Pro-tip: 1B or 3B models are 5x faster for this specific task
            model="llama3.2:1b-instruct-q4_K_M", 
            options={
                "temperature": 0,
                "num_predict": 10, # Reduced from 12 (we only need ~3 tokens)
                "num_ctx": 2048,   # Reduced from 4096 to save VRAM
            }
        )
    except Exception as e:
        return top_candidates[:k]

    # --- REFINED PARSING ---
    if not res or "NONE" in res.upper(): return []
    
    # Grab all digits and filter for valid indices
    found_ids = [int(i) - 1 for i in re.findall(r"\d+", res)]
    final = [top_candidates[i] for i in found_ids if 0 <= i < len(top_candidates)]
    
    # Final Deduplication & Fallback
    seen = set()
    deduped = [x for x in final if not (x in seen or seen.add(x))]
    
    return deduped[:k] if deduped else top_candidates[:k]