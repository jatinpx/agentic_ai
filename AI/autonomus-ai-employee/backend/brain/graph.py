import re
import uuid
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from tools.registry import get_tool, list_tools
from tools.registry import execute_tool, list_available_tools
from services.memory_service import store_memory, recall_memory
from services.memory_picker import pick_memory_for_role
from services.llm_client import chat


# --- OPTIONAL: Mock logger if brain.logger is not present ---
try:
    from brain.logger import add_log
except ImportError:
    def add_log(msg): print(f"[LOG] {msg}")

def log_event(stage: str, step_id: str, message: str):
    add_log(f"[STAGE:{stage}] [STEP:{step_id}] {message}")

# ==========================================
# MODEL CONFIGURATION PER NODE
# ==========================================
# Configure the ollama model for each node
MODEL_PLANNER = "llama3.1:latest" # You can adjust this to a more powerful model if available
MODEL_EXECUTOR = "llama3.1:latest"
MODEL_CRITIC = "llama3.1:latest" # You can adjust this to a more powerful model if available
MODEL_IMPROVER = "llama3.1:latest" # You can adjust this to a more powerful model if available

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
    user_input = state["user_input"]
    iteration = state.get("iteration_count", 0) + 1
    
    feedback = state.get("critique_feedback", "")
    is_replan = iteration > 1

    # 1. Fetch raw memories (list of tuples)
    raw_mem_tuples = recall_memory(user_input, limit=8)
    
    # 2. Extract just the strings for the picker
    raw_mem_strings = [m[0] for m in raw_mem_tuples if m[0]]
    
    # 3. Pick the best ones (Returns List[str])
    picked = pick_memory_for_role(user_input, raw_mem_strings, role="planner", k=3)
    
    # FIX: 'picked' is now just a list of strings
    memo = "\n".join([f"- {m}" for m in picked])

    print(f"\n🧠 [PLANNER] Iteration {iteration} | Re-planning: {is_replan}")
    # ... rest of node ...
    if is_replan:
        print(f"❌ Previous Feedback: {feedback}")

    # 3. Dynamic Prompt Construction
    # We add a specific section for "CRITIQUE" if we are in a loop
    critique_section = f"\n### ❌ FEEDBACK FROM PREVIOUS ATTEMPT:\n{feedback}\nYOU MUST ADDRESS THIS FEEDBACK IN YOUR NEW PLAN." if is_replan else ""

    prompt = f"""
You are a senior autonomous AI planner. Your goal is to provide a plan that is highly specific, technical, and avoids generic summaries.

{critique_section}

RELEVANT PAST EXPERIENCE:
{memo}

USER GOAL:
{user_input}

AVAILABLE TOOLS:
- web_search  → Use for specific technical data, newest facts, and detailed specs.
- python_exec → Use for data processing, math, or structuring logic.
- NONE        → Use for final reasoning and synthesis.

STRICT PLANNING RULES:
1. Output ONLY numbered steps.
2. Each step MUST end with: | TOOL: tool_name
3. If the previous attempt was "too generic", break your search steps into specific sub-topics (e.g., instead of "Search AI", use "Search for Agentic AI memory architectures and tool-use patterns").
4. Ensure the plan includes a specific step for "Checking for technical details" to satisfy a strict critic.
5. Max 5 steps. No intro/outro.

EXAMPLE OF SPECIFIC PLANNING:
1. Search for specific technical architectures of {user_input} | TOOL: web_search
2. Look for real-world case studies and industry-specific metrics | TOOL: web_search
3. Synthesize technical specs into a detailed report | TOOL: NONE
"""

    raw_text = chat(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_PLANNER
    )

    # --- Standard Cleaning Logic ---
    raw_text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    parsed_steps = []

    for line in lines:
        if not re.match(r"^\d+[\.\)]", line): continue
        step_body = re.sub(r"^\d+[\.\)]\s*", "", line).strip()
        tool_match = re.search(r"\|\s*TOOL\s*:\s*(\w+)", step_body, re.IGNORECASE)
        
        if tool_match:
            tool_name = tool_match.group(1).lower()
            step_text = re.sub(r"\|\s*TOOL\s*:\s*\w+", "", step_body, flags=re.IGNORECASE).strip()
        else:
            tool_name = "none"
            step_text = step_body
        
        if tool_name not in ["web_search", "python_exec", "none"]: tool_name = "none"
        parsed_steps.append(f"{step_text} | TOOL: {tool_name}")

    if not parsed_steps:
        parsed_steps = [f"Search for deep technical details on {user_input} | TOOL: web_search", "Analyze findings | TOOL: NONE"]

    log_event("planner", f"iter-{iteration}", f"Plan created. Addressing feedback: {is_replan}")

    return {
        "plan": parsed_steps[:5],
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

    text = chat(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_EXECUTOR
    )

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

from tools.registry import get_tool # Ensure this is your actual tool loader

def executor_node(state: AgentState):
    plan = state["plan"]
    results = []
    context = ""
    
    # 1. Fetch raw tuples
    raw_mem_tuples = recall_memory(state["user_input"], limit=6)
    
    # 2. Convert to strings for the picker
    raw_mem_strings = [m[0] for m in raw_mem_tuples if m[0]]
    
    # 3. Pick best (Returns List[str])
    picked = pick_memory_for_role(state["user_input"], raw_mem_strings, role="executor", k=2)
    
    print("\n🧠 [EXECUTOR MEMORY PICKED]:")
    for content in picked:
        # FIX: content is a string, no distance available here
        print(f"- {content[:120]}...")
        context += f"\n[PAST EXPERIENCE] {content}\n"

    # ... rest of node ...




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

        llm_output = chat(
            messages=[{"role": "user", "content": prompt}],
            model=MODEL_EXECUTOR
        )
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

    summary = chat(
        messages=[{"role": "user", "content": summary_prompt}],
        model=MODEL_EXECUTOR
    )
    
    # avoid storing useless or duplicate memory
    clean_summary = summary.strip()

    # ... inside executor_node ...
    if len(clean_summary) > 60:
        # Search for the 1 most similar memory
        existing = recall_memory(clean_summary, limit=1)
        
        should_save = True
        if existing:
            content, distance = existing[0]
            print(f"📊 [MEMORY CHECK] Closest match distance: {distance:.4f}")
            
            # If distance is very small, it's a duplicate.
            # Adjust 0.1 based on your specific embedding model's sensitivity.
            if distance < 0.1:
                print("⚠️ [SKIP] Similar experience already exists in memory.")
                should_save = False

        if should_save:
            store_memory(
                content=clean_summary,
                mem_type="experience",
                task_id=str(uuid.uuid4())
            )
            print("\n🧠 [MEMORY STORED]:", clean_summary[:120])


        

    return {"results": results, "iteration_count": state.get("iteration_count", 0)}

def critic_node(state: AgentState):
    """
    Constructive Critic Node.
    Forces specific, actionable feedback and prevents vague 'refine' loops.
    
    :param state: Description
    :type state: AgentState
    """
    print("🧪 [CRITIC] Reviewing work...")
    user_query = state.get("user_input", "Unknown query")
    iteration = state.get("iteration_count", 1)
    
    # 1. Fetch raw tuples
    raw_memories_tuples = recall_memory(user_query, limit=5)
    
    # 2. Extract strings
    raw_mem_strings = [m[0] for m in raw_memories_tuples if m[0]]
    
    # 3. Pick (Returns List[str])
    selected_memories = pick_memory_for_role(user_query, raw_mem_strings, role="critic", k=2)
    
    # FIX: selected_memories is List[str]
    failure_context = "\n".join([m for m in selected_memories]) if selected_memories else "None"
    
    # ... rest of node ...

    # 2. Results to Review
    combined_results = "\n".join(state.get("results", []))

    # 3. Constructive Prompt
    # We tell the Critic to be more lenient if we've already tried 3 times.
    strictness = "high" if iteration < 3 else "moderate"

    prompt = f"""
            You are a Technical Quality Auditor (Strictness: {strictness}).
            Review the content below against the User Query.

            ### USER QUERY: 
            '{user_query}'

            ### CONTENT TO REVIEW:
            {combined_results}

            ### PAST MISTAKES TO WATCH FOR:
            {failure_context}

            ### CRITICAL RULES:
            1. **Actionable Feedback**: If you FAIL the content, you MUST specify exactly what is missing (e.g., "Missing current market cap for Nvidia" instead of "Refine results").
            2. **The 80/20 Rule**: If the content is factually correct and answers the main prompt, lean towards [PASS]. Do not fail for minor stylistic choices.
            3. **No Hallucinations**: If the agent used phrases like "I don't have real-time data" or "Placeholder", it MUST [FAIL].
            4. **Specificity**: Check for actual numbers, dates, and names.

            ### FORMAT:
            Thinking: [Your reasoning]
            Status: [PASS] or [FAIL]
            Feedback: [If FAIL: One specific instruction for the planner. If PASS: "Excellent work."]
            """

    response = chat(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_CRITIC
    )

    # 4. Cleaning & Parsing
    clean_content = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()
    
    # Robust Status Detection
    status = "FAIL" if "Status: [FAIL]" in clean_content or "STATUS: FAIL" in clean_content.upper() else "PASS"
    
    # Force specificity: if the model gives a generic "Refine results", we override it
    feedback_match = re.search(r'Feedback:\s*(.*)', clean_content, re.IGNORECASE)
    feedback = feedback_match.group(1) if feedback_match else "Content is too generic; need more specific technical data."
    
    if status == "FAIL" and len(feedback) < 15:
        feedback = "Provide more specific details, numbers, and technical specs relevant to the query."

    print(f"🧪 Critic Verdict: {status} | Iteration: {iteration}")
    log_event("critic", f"iter-{iteration}", f"Verdict: {status} | Feedback: {feedback}")

    # 5. Memory Storage (Only store unique learnings)
    new_learning = f"Task: {user_query}\nFeedback: {feedback}"
    if status == "FAIL" and len(feedback) > 15:
        existing = recall_memory(new_learning, limit=1)
        if not existing or existing[0][1] > 0.1: # Distance check
            store_memory(content=new_learning, mem_type="learning")
            print("🧠 [CRITIC] New failure-prevention memory stored.")

    return {
        "critique_status": status,
        "critique_feedback": feedback,
        "critique": "RETRY" if status == "FAIL" else "PASS"
    }

def improve_node(state: AgentState):
    """
    Final Salvage & Polish Node.
    Synthesizes raw tool outputs into a professional report, 
    addressing any lingering Critic concerns.
    """
    print("✨ [IMPROVER] Finalizing report...")
    log_event("improve", "init", "Finalizing report.")

    user_query = state.get("user_input", "")
    results = state.get("results", [])
    last_feedback = state.get("critique_feedback", "None")
    status = state.get("critique_status", "PASS")

    # Combine all execution results into a single context
    combined_raw_data = "\n\n".join(results)

    # If the Critic failed this, we tell the Improver to "Salvage" it
    instruction = (
        "The technical critic was NOT fully satisfied. Use your reasoning to patch any gaps "
        f"mentioned in this feedback: '{last_feedback}'."
        if status == "FAIL" else 
        "The technical critic approved this work. Focus on professional formatting and clarity."
    )

    prompt = f"""
You are a Senior Technical Writer and Data Analyst.
Your goal: Transform raw tool outputs into a high-quality, professional report.

### ORIGINAL USER QUERY:
{user_query}

### RAW DATA & FINDINGS:
{combined_raw_data}

### FINAL INSTRUCTION:
{instruction}

### REPORT REQUIREMENTS:
1. **Executive Summary**: A concise 2-3 sentence overview.
2. **Detailed Analysis**: Organize findings with clear headers.
3. **Fact-First**: Ensure all numbers, names, and dates from the raw data are preserved.
4. **Clean Exit**: Remove any tool artifacts like '[WEB_SEARCH RESULT]' or 'Python code output'.
5. **No Fluff**: If specific data is missing, admit it professionally rather than hallucinating.

Format the output in clean Markdown.
"""

    response = chat(
        messages=[{"role": "user", "content": prompt}],
        model=MODEL_IMPROVER
    )

    # Final cleanup of any lingering 'thinking' tags
    final_answer = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()

    print("✨ Report finalized and polished.")
    log_event("improve", "init", "Report finalized.")
    
    return {"final_answer": final_answer}

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