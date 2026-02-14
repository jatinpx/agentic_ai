import ollama
import json
import re

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

    response = ollama.chat(
        model="phi3",
        messages=[
            {"role": "system", "content": PLANNER_PROMPT},
            {"role": "user", "content": user_goal}
        ]
    )

    content = response["message"]["content"]

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
