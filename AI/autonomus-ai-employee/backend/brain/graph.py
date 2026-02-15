import re
import uuid
import ollama
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from tools.registry import get_tool, list_tools
from tools.registry import execute_tool, list_available_tools
from services.memory_service import store_memory, recall_memory
from services.memory_picker import pick_memory_for_role


# --- OPTIONAL: Mock logger if brain.logger is not present ---
try:
    from brain.logger import add_log
except ImportError:
    def add_log(msg): print(f"[LOG] {msg}")

def log_event(stage: str, step_id: str, message: str):
    add_log(f"[STAGE:{stage}] [STEP:{step_id}] {message}")

# ==========================================
# 1. STATE DEFINITION
# ==========================================
class AgentState(TypedDict):
    user_input: str
    plan: List[str]
    results: List[str]
    final_answer: str
    critique: str           # Keeping for legacy/compatibility
    critique_status: str    # Added for clarity
    critique_feedback: str  # Added for clarity
    iteration_count: int

# ==========================================
# 2. NODES (The "Brains")
# ==========================================

def planner_node(state: AgentState):
    """
    High-discipline planning node.
    Produces deterministic, tool-aware execution plans.
    """

    user_input = state["user_input"]
    iteration = state.get("iteration_count", 0) + 1
    
    raw_mem = recall_memory(user_input, limit=8)
    picked = pick_memory_for_role(user_input, raw_mem, role="planner", k=2)
    memo = "\n".join(picked)

    
    print("\n🧠Memory Retrieved:")
    for m in memo.split("\n"):
        print(f"- {m[:150]}...")  # Print a snippet of each memory for debugging


    print("\n🧠 [PLANNER] Strategizing with Tool Awareness...")
    log_event("planner", "init", "Creating strategic plan.")

    # =========================
    # STRICT PLANNER PROMPT
    # =========================
    prompt = f"""
You are a senior autonomous AI planner.

RELEVANT PAST EXPERIENCE (Use this to avoid repeating work and improve planning):
{memo}
User goal:
{user_input}

Available tools:
- web_search  → use for internet or latest factual info
- python_exec → use for calculations, parsing, data extraction, structuring
- NONE        → use for reasoning, comparison, writing

Your job:
Create a precise execution plan.

STRICT RULES:
1. Output ONLY numbered steps.
2. Each step MUST end with: | TOOL: tool_name
3. Allowed tools ONLY: web_search, python_exec, NONE
4. NEVER mention tool inside step text.
5. If getting info → web_search
6. If extracting/calculating → python_exec
7. If analyzing/writing → NONE
8. No intro text
9. No markdown
10. Max 5 steps

EXAMPLE:
1. Search latest Nvidia GPU prices | TOOL: web_search
2. Extract price numbers from results | TOOL: python_exec
3. Compare models | TOOL: NONE
4. Format final answer | TOOL: NONE
"""

    response = ollama.chat(
        model="deepseek-r1:7b",
        messages=[{"role": "user", "content": prompt}]
    )

    raw_text = response["message"]["content"]

    # remove thinking blocks
    raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()

    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    parsed_steps = []

    # =========================
    # CLEAN PARSING
    # =========================
    for line in lines:

        # accept numbered lines only
        if not re.match(r"^\d+[\.\)]", line):
            continue

        # remove leading number formatting
        step_body = re.sub(r"^\d+[\.\)]\s*", "", line).strip()

        # check tool tag
        tool_match = re.search(r"\|\s*TOOL\s*:\s*(\w+)", step_body, re.IGNORECASE)

        if tool_match:
            tool_name = tool_match.group(1).lower()
            step_text = re.sub(r"\|\s*TOOL\s*:\s*\w+", "", step_body, flags=re.IGNORECASE).strip()
        else:
            tool_name = "none"
            step_text = step_body

        # safety: restrict tools
        if tool_name not in ["web_search", "python_exec", "none"]:
            tool_name = "none"

        parsed_steps.append(f"{step_text} | TOOL: {tool_name}")

    # =========================
    # FALLBACK if model fails
    # =========================
    if not parsed_steps:
        parsed_steps = [
            f"Search information related to {user_input} | TOOL: web_search",
            "Analyze gathered information | TOOL: NONE",
            "Prepare final structured response | TOOL: NONE"
        ]

    # limit steps
    parsed_steps = parsed_steps[:5]

    print(f"🧠 Strategic Plan: {parsed_steps}")
    log_event("planner", "init", f"Plan created with {len(parsed_steps)} steps.")

    return {
        "plan": parsed_steps,
        "results": [],
        "iteration_count": iteration
    }


def human_approval_node(state: AgentState):
    """Placeholder node for the 'interrupt_before' breakpoint."""
    print("\n⏸️ [PAUSE] Plan ready for human review.")
    log_event("approval", "init", "Plan ready for human review. Awaiting approval to execute.")
    return state

def decide_tool_for_step(step_text: str, context: str):
    """
    LLM decides whether tool is required.
    """

    tools = list_available_tools()

    prompt = f"""
You are an expert autonomous AI execution engine.

Your job: decide if a tool is REQUIRED.

STRICT RULES:

Use web_search ONLY if:
- Need latest info
- Need internet data
- Need real-time prices/news

Use python_exec ONLY if:
- Calculations needed
- Data parsing
- Code execution
- Converting numbers

Use NONE if:
- Summarizing
- Comparing
- Explaining
- Writing report
- Formatting

Task:
{step_text}

Context:
{context}

Available tools:
{tools}

Respond STRICTLY:

TOOL: tool_name or NONE
INPUT: exact input for tool
"""

    response = ollama.chat(
        model="qwen2.5:7b-instruct",
        messages=[{"role": "user", "content": prompt}]
    )

    text = response["message"]["content"]

    tool = "NONE"
    tool_input = step_text

    for line in text.split("\n"):
        if "TOOL:" in line:
            tool = line.split("TOOL:")[1].strip()
        if "INPUT:" in line:
            tool_input = line.split("INPUT:")[1].strip()

    # safety fallback
    if tool not in tools and tool != "NONE":
        tool = "NONE"

    return tool, tool_input


import re
import ollama
from tools.registry import get_tool # Ensure this is your actual tool loader

def executor_node(state: AgentState):
    plan = state["plan"]
    results = []
    context = ""
    
    # 🔍 recall memory for execution context
    raw_mem = recall_memory(state["user_input"], limit=6)
    picked = pick_memory_for_role(state["user_input"], raw_mem, role="executor", k=2)
    context += "\n".join(picked)
    print("\n🧠 [EXECUTOR MEMORY PICKED]:")
    for m in picked:
        print("-", m[:120])




    print(f"🔍 [EXECUTOR] Processing {len(plan)} steps...")
    log_event("executor", "init", f"Starting execution of {len(plan)} strategic steps.")

    for i, step in enumerate(plan):
        # 1. PARSE THE STEP AND TOOL
        # This regex splits "Search for Nvidia prices | TOOL: web_search"
        match = re.search(r"^(.*?)\s*\|\s*TOOL:\s*(\w+)", step, re.IGNORECASE)
        
        if match:
            step_text = match.group(1).strip()
            tool_name = match.group(2).strip().lower()
        else:
            # Fallback if the Planner forgot the pipe symbol
            step_text = step.strip()
            tool_name = "none"

        # 2. CLEAN THE QUERY
        # Remove leading numbers (e.g., "1. ") and markdown bolding (**)
        clean_step = re.sub(r"\*\*|\*", "", step_text)
        clean_query = re.sub(r"^\d+[\.\)]\s*", "", clean_step).strip()
        step_id = f"step-{i + 1}"

        print(f"  -> Step {i+1}/{len(plan)}: [{tool_name.upper()}]")
        log_event("executor", step_id, f"Executing: {clean_query} (tool={tool_name})")

        # 3. TOOL EXECUTION PATH
        if tool_name != "none":
            log_event("executor", step_id, f"Calling tool: {tool_name}.")
            
            tool_func = get_tool(tool_name)
            if tool_func:
                try:
                    # Execute the actual tool
                    tool_output = tool_func(clean_query)
                    
                    # Store result and update rolling context
                    formatted_res = f"[{tool_name.upper()} RESULT] {tool_output}"
                    results.append(formatted_res)
                    context += f"\n{formatted_res}\n"
                    
                    log_event("executor", step_id, f"Tool {tool_name} completed successfully.")
                    continue # Skip LLM reasoning for this step
                except Exception as e:
                    error_msg = f"❌ Tool {tool_name} failed: {str(e)}"
                    log_event("executor", step_id, error_msg)
                    results.append(error_msg)
            else:
                log_event("executor", step_id, f"Tool '{tool_name}' not found in registry. Falling back to LLM.")

        # 4. LLM REASONING PATH (Default/Fallback)
        log_event("executor", step_id, "Reasoning with LLM.")
        
        # We give the LLM all previous context so it knows what the tools found
        prompt = (
            f"PREVIOUS CONTEXT:\n{context}\n\n"
            f"CURRENT TASK: {clean_query}\n"
            "INSTRUCTION: Use the context provided to complete this task accurately."
        )

        response = ollama.chat(
            model="qwen2.5:7b-instruct",
            messages=[{"role": "user", "content": prompt}]
        )

        llm_output = response["message"]["content"]
        results.append(llm_output)
        context += f"\n[REASONING] {llm_output}\n"

    log_event("executor", "init", "Execution phase finalized.")
    
    summary_prompt = f"""
        Summarize key learnings from this execution in 5-6 lines.

        Task:
        {state['user_input']}

        Execution result:
        {' '.join(results)}

        Focus:
        - final findings
        - key numbers
        - conclusions
        - important decisions
        """

    summary = ollama.chat(
        model="qwen2.5:7b-instruct",
        messages=[{"role": "user", "content": summary_prompt}]
    )["message"]["content"]
    
    # avoid storing useless or duplicate memory
    clean_summary = summary.strip()

    if len(clean_summary) > 60:  # ignore weak runs
        existing = recall_memory(clean_summary, limit=1)

        # only store if not semantically similar memory exists
        if not existing:
            store_memory(
                content=clean_summary,
                mem_type="experience",
                task_id=str(uuid.uuid4())
            )
            print("\n🧠 MEMORY STORED:", clean_summary[:120])


        

    return {"results": results, "iteration_count": state.get("iteration_count", 0)}

def critic_node(state: AgentState):
    """
    Critic reviews output for accuracy, relevance and hallucinations.
    Uses past failure memory to improve judgement.
    """

    print("🧪 [CRITIC] Reviewing work...")
    log_event("critic", "init", "Reviewing results for relevance and accuracy.")

    # ---------------------------------------------------
    # 1. GET USER QUERY
    # ---------------------------------------------------
    user_query = state.get("user_input", "Unknown query")

    # ---------------------------------------------------
    # 2. RETRIEVE MEMORY FROM DB
    # ---------------------------------------------------
    raw_memories = recall_memory(user_query, limit=8)

    # ---------------------------------------------------
    # 3. PICK ONLY FAILURE / LEARNING MEMORIES
    # ---------------------------------------------------
    try:
        from services.memory_picker import pick_memory_for_role

        selected_memories = pick_memory_for_role(
            query=user_query,
            memories=raw_memories,
            role="critic",
            k=2
        )
    except Exception:
        # fallback if picker fails
        selected_memories = raw_memories[:2]

    # ---------------------------------------------------
    # 4. BUILD FAILURE CONTEXT
    # ---------------------------------------------------
    failure_context = "\n".join(selected_memories) if selected_memories else "None"

    # debug visibility
    print("\n🧠 [CRITIC MEMORY USED]:")
    for m in selected_memories:
        print("-", m[:150])

    # ---------------------------------------------------
    # 5. COMBINE CURRENT RESULTS
    # ---------------------------------------------------
    combined = "\n".join(state.get("results", []))
    
    # 3. Enhanced Prompt
    prompt = (
        f"You are a strict technical Editor. Review the content below based on the User Query.\n\n"
        f"### USER QUERY: '{user_query}'\n\n"
        f"### CONTENT TO REVIEW:\n{combined}\n\n"
        f"### PAST MISTAKES or FAILURES (if any):\n{failure_context}\n\n"
        f"### INSTRUCTIONS:\n"
        f"1. **Relevance**: Does this directly answer the specific user query? (Ignore generic intros like 'Executive Summary').\n"
        f"2. **Accuracy**: Are there actual numbers/specs? Flag any code that uses 'Hypothetical' or 'Example' values.\n"
        f"3. **Completeness**: Is important info missing?\n\n"
        f"### FORMAT (Strictly follow this):\n"
        f"Thinking: [Brief reasoning]\n"
        f"Status: [PASS] or [FAIL]\n"
        f"Feedback: [One clear sentence on what to fix if FAIL]"
    )

    response = ollama.chat(
        model="deepseek-r1:7b",
        messages=[{"role": "user", "content": prompt}]
    )

    # 4. Clean and Parse Response
    # DeepSeek-R1 often includes <think> tags. We want the final verdict.
    raw_content = response["message"]["content"]
    
    # Remove thinking traces for cleaner logging (optional, but good for parsing)
    clean_content = re.sub(r'<think>.*?</think>', '', raw_content, flags=re.DOTALL).strip()
    
    # Robust status detection
    if "[FAIL]" in clean_content or "FAIL" in clean_content.upper():
        status = "FAIL"
    elif "[PASS]" in clean_content or "PASS" in clean_content.upper():
        status = "PASS"
    else:
        # Fallback: If it criticizes heavily, default to FAIL
        status = "FAIL" if "missing" in clean_content.lower() or "hypothetical" in clean_content.lower() else "PASS"

    print(f"🧪 Critic Verdict: {status}")
    
    # Extract feedback if it exists
    feedback_match = re.search(r'Feedback:\s*(.*)', clean_content, re.IGNORECASE)
    feedback = feedback_match.group(1) if feedback_match else "Refine search results."

    log_event("critic", "init", f"Verdict: {status} | Feedback: {feedback}")
    store_memory(
    content=f"Task: {user_query}\nVerdict: {status}\nFeedback: {feedback}",
    mem_type="learning"
)


    # 5. Return structured output that your graph can use to loop back
    return {
        "critique_status": status,  # Use this key in your Conditional Edge
        "critique_feedback": feedback,
        "critique": "RETRY" if status == "FAIL" else "PASS" # Kept for the legacy conditional check
    }

def improve_node(state: AgentState):
    """Final polish/formatting."""
    print("✨ [IMPROVER] Finalizing report...")
    log_event("improve", "init", "Finalizing report.")
    combined = "\n".join(state["results"])

    prompt = f"Format and polish this into a professional final report:\n{combined}"

    response = ollama.chat(
        model="qwen2.5:7b-instruct",
        messages=[{"role": "user", "content": prompt}]
    )

    print("✨ Report finalized.")
    log_event("improve", "init", "Report finalized.")
    return {"final_answer": response["message"]["content"]}

# ==========================================
# 3. GRAPH CONSTRUCTION
# ==========================================

def build_full_agent():
    memory = MemorySaver()
    graph = StateGraph(AgentState)

    # Add Nodes
    graph.add_node("planner", planner_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("executor", executor_node)
    graph.add_node("critic", critic_node)
    graph.add_node("improve", improve_node)

    # Set Entry
    graph.set_entry_point("planner")

    # Edges
    graph.add_edge("planner", "human_approval")
    graph.add_edge("human_approval", "executor")
    graph.add_edge("executor", "critic")

    # The Decision Loop (Reflexion Pattern)
    graph.add_conditional_edges(
    "critic",
    lambda state: "planner" if (
        state.get("critique_status") == "FAIL" and 
        state.get("iteration_count", 0) < 3
    ) else "improve"
)

    graph.add_edge("improve", END)

    # Compile with Breakpoint
    return graph.compile(checkpointer=memory, interrupt_before=["human_approval"])