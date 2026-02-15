import json
import re

from agent.memory import store_memory, recall_memory
from agent.critic import review_answer
from tools.search import web_search
from tools.file_tools import save_to_file
from services.llm_client import chat

def calculator(expression: str):
    try:
        return str(eval(expression))
    except:
        return "Error"

TOOLS = {
    "calculator": calculator,
    "search": web_search,
    "save": save_to_file
}

SYSTEM_PROMPT = """
You are an AI agent with tools.

Tools:
calculator(expression)
search(query)
save(text)

Return JSON:
{ "tool": "...", "input": "..." }
OR
{ "tool": "none", "response": "..." }
"""

def run_agent(user_input):

    past = recall_memory(user_input)
    context = f"Past memory:\n{past}\n\nUser:{user_input}"

    content = chat(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ],
        model="phi3"
    ).strip()
    match = re.search(r'\{[^{}]*\}', content)

    if not match:
        return content

    data = json.loads(match.group(0))
    tool = data.get("tool","").lower()

    if tool == "none":
        reply = data.get("response","")

        verdict = review_answer(user_input, reply)
        if "IMPROVE" in verdict:
            reply = chat(
                messages=[
                    {"role": "user", "content": f"Improve:\n{reply}"}
                ],
                model="phi3"
            )

        store_memory(f"{user_input} -> {reply}")
        return reply

    if tool in TOOLS:
        result = TOOLS[tool](data.get("input",""))

        verdict = review_answer(user_input, result)
        if "IMPROVE" in verdict:
            result = chat(
                messages=[
                    {"role": "user", "content": f"Improve:\n{result}"}
                ],
                model="phi3"
            )

        store_memory(f"{user_input} -> {result}")
        return result

    return "Done"
