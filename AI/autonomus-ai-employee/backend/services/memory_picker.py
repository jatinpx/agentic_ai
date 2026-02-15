import ollama

def pick_memory_for_role(query: str, memories: list[str], role: str, k: int = 2):
    """
    role = planner | executor | critic
    """

    if not memories:
        return []

    mem_blob = "\n\n".join([f"{i+1}. {m}" for i, m in enumerate(memories)])

    prompt = f"""
You are selecting memories for an AI agent.

ROLE: {role}
CURRENT TASK: {query}

MEMORIES:
{mem_blob}

Selection rules:
- planner → pick strategic past tasks
- executor → pick factual/knowledge memories
- critic → pick past mistakes/failures
- ignore irrelevant
- choose max {k}

Return ONLY memory numbers.
Example: 1,3
"""

    res = ollama.chat(
        model="qwen2.5:7b-instruct",
        messages=[{"role": "user", "content": prompt}]
    )["message"]["content"]

    nums = []
    for p in res.replace(" ", "").split(","):
        if p.isdigit():
            nums.append(int(p)-1)

    return [memories[i] for i in nums if 0 <= i < len(memories)][:k]
