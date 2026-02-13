import ollama
import json
from memory import store_memory, recall_memory
from planner import create_plan
from critic import review_answer



def calculator(expression: str):
    try:
        return str(eval(expression))
    except:
        return "Error"
    

def save_to_file(text: str):
    with open("output.txt", 'a') as f:
        f.write(text + "\n")
    return "saved to file"

def web_search(query: str):
    #mock web search for now
    return f"Search results for '{query}': AI is growing rapidly in 2026."


TOOLS={
    "calculator":calculator,
    "search":web_search,
    "save":save_to_file
}


#---------------agent brain-----------
SYSTEM_PROMPT = """
You are an AI agent that can use tools.

Available tools:
1. calculator(expression)
2. save(text)
3. search(query)

If math → use calculator  
If user asks to save → use save  
If user asks info/news → use search  

Reply ONLY in JSON format:
{
 "tool": "tool_name",
 "input": "what to pass"
}

If no tool needed:
{
 "tool": "none",
 "response": "your answer"
}

"""


def run_agent(user_input):

    past = recall_memory(user_input)
    context = f"Past interactions:\n{past}\n\nCurrent query:\n{user_input}"

    response = ollama.chat(
        model='phi3',
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ]
    )

    import re
    content = response["message"]["content"].strip()

    # extract JSON safely
    match = re.search(r'\{[^{}]*\}', content, re.DOTALL)
    if not match:
        return f"Could not find JSON in:\n{content}"

    json_text = match.group(0)

    try:
        data = json.loads(json_text)
    except Exception as e:
        return f"JSON parse error: {e}\nExtracted:\n{json_text}"

    tool = data.get("tool", "").lower().strip()

    # normalize tool names
    if tool in ["math", "calc"]:
        tool = "calculator"
    if tool in ["write", "save_file"]:
        tool = "save"
    if tool in ["google", "web"]:
        tool = "search"

    # ---------------- NO TOOL CASE ---------------- #
    if tool == "none":
        reply = data.get("response", "")

        # reflection check
        verdict = review_answer(user_input, reply)

        if "IMPROVE" in verdict:
            improved = ollama.chat(
                model="phi3",
                messages=[
                    {"role": "system", "content": "Improve this answer and make it more helpful."},
                    {"role": "user", "content": reply}
                ]
            )
            reply = improved["message"]["content"]

        store_memory(f"User: {user_input}\nAgent: {reply}")
        return reply

    # ---------------- TOOL CASE ---------------- #
    if tool in TOOLS:
        result = TOOLS[tool](data.get("input", ""))

        # reflection check
        verdict = review_answer(user_input, result)

        if "IMPROVE" in verdict:
            improved = ollama.chat(
                model="phi3",
                messages=[
                    {"role": "system", "content": "Improve this answer and make it more useful."},
                    {"role": "user", "content": result}
                ]
            )
            result = improved["message"]["content"]

        store_memory(f"User: {user_input}\nAgent used {tool} got result {result}")
        return f"[Tool {tool} used]\nResults: {result}"

    # ---------------- FALLBACK ---------------- #
    fallback = ollama.chat(
        model="phi3",
        messages=[
            {"role": "system", "content": "You are a helpful AI assistant."},
            {"role": "user", "content": user_input}
        ]
    )

    reply = fallback["message"]["content"]
    store_memory(f"User: {user_input}\nAgent: {reply}")
    return reply


#loop

if __name__ == "__main__":
    print("Agent ready. Type 'exit' to quit.\n")

    while True:
        user = input("You: ")
        if user.lower() == "exit":
            break

        # create plan
        steps = create_plan(user)

        if steps:
            print("\n🧠 Plan:")
            for i, step in enumerate(steps, 1):
                print(f"{i}. {step}")

            print("\n⚡ Executing...\n")

            for step in steps:
    
    # if step is dict, convert to string
                if isinstance(step, dict):
                    step = list(step.values())[0]

                print(f"\n⚙️ Executing step: {step}\n")
                output = run_agent(step)
                print("→", output)


        else:
            output = run_agent(user)
            print("Agent:", output)
