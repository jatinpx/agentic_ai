import json
import re

from services.llm_client import chat

PLANNER_PROMPT = """
Break the user request into simple steps.

Return ONLY valid JSON:
{
  "steps": [
    "step 1",
    "step 2",
    "step 3"
  ]
}
"""

def create_plan(user_goal):

    content = chat(
        messages=[
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": user_goal}
        ],
        model="phi3"
    )

    # extract json safely
    match = re.search(r'\{.*\}', content, re.DOTALL)
    if not match:
        return []

    json_text = match.group()

    # clean common LLM issues
    json_text = json_text.replace("'", '"')

    try:
        data = json.loads(json_text)
        return data.get("steps", [])
    except:
        print("Planner JSON error, using fallback")
        return [user_goal]  # fallback single step
