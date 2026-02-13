import ollama
import json
import re

PLANNER_PROMPT = """
You are a planning AI.

Break the user request into clear numbered steps.

Return ONLY JSON:
{
 "steps": [
   "step 1",
   "step 2",
   "step 3"
 ]
}
"""

def create_plan(user_goal):

    response = ollama.chat(
        model="phi3",
        messages=[
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": user_goal}
        ]
    )

    content = response["message"]["content"]

    match = re.search(r'\{.*\}', content, re.DOTALL)
    if not match:
        return []

    data = json.loads(match.group())
    return data.get("steps", [])
