from langgraph.graph import StateGraph, END
from typing import TypedDict, List
import ollama

# ---- STATE ---- #
class AgentState(TypedDict):
    user_input: str
    plan: List[str]
    results: List[str]
    final_answer: str


# ---- PLANNER NODE ---- #
def planner_node(state: AgentState):
    user_input = state["user_input"]

    prompt = f"""
Break this task into steps:
{user_input}

Return simple numbered steps.
"""

    response = ollama.chat(
        model="llama3",
        messages=[{"role": "user", "content": prompt}]
    )

    text = response["message"]["content"]
    steps = [s.strip() for s in text.split("\n") if s.strip()]

    return {"plan": steps, "results": []}


# ---- EXECUTOR NODE ---- #
def executor_node(state: AgentState):
    plan = state["plan"]
    results = []

    for step in plan:
        response = ollama.chat(
            model="llama3",
            messages=[{"role": "user", "content": step}]
        )

        results.append(response["message"]["content"])

    return {"results": results}


# ---- FINAL NODE ---- #
def final_node(state: AgentState):
    combined = "\n".join(state["results"])

    response = ollama.chat(
        model="llama3",
        messages=[
            {"role": "system", "content": "Summarize clearly"},
            {"role": "user", "content": combined}
        ]
    )

    return {"final_answer": response["message"]["content"]}


# ---- BUILD GRAPH ---- #
def build_graph():

    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("final", final_node)

    graph.set_entry_point("planner")

    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "final")
    graph.add_edge("final", END)

    return graph.compile()
