import ollama
import json


def calcullator(expression: str):
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
    "calcullator":calcullator,
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
    response=ollama.chat(
    model='phi3',
    messages=[{"role":"system", "content":SYSTEM_PROMPT},
              {"role":'user', "content": user_input}
              ]
    )
    
    content= response["message"]["content"]
    
    try:
        data=json.loads(content)
    except:
        return f"LLM formatting error:\n{content}"
    
    tool =data,get("tool")
    
    if(tool)=="none":
        return data.get("response")
    
    if tool in TOOLS:
        result=TOOLS[tool](date.get("input", ""))
        return f"[Tool {tool} used]\nResults:{result}"
    
    return "unknown tool"


#loop

if __name__ == "__main__":
    print("Agent ready. Type 'exit' to quit.\n")

    while True:
        user = input("You: ")
        if user.lower() == "exit":
            break

        output = run_agent(user)
        print("Agent:", output)