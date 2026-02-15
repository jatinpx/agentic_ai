import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import os
from services.memory_service import store_memory, recall_memory


# Importing your logic from the other files
from brain.graph import build_full_agent # Ensure your graph file has this function
from brain.logger import set_thread_id, clear_thread_id

app = FastAPI()

# Global graph instance (MemorySaver is inside build_full_agent)
graph = build_full_agent()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELS ---
class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None # For resuming existing sessions

class ApprovalRequest(BaseModel):
    thread_id: str
    approve: bool
    edited_plan: Optional[List[str]] = None # Optional: user can send back a modified plan

# --- ENDPOINTS ---

@app.get("/")
def home():
    return {"status": "AI Employee (Advanced Mode) running"}

@app.post("/chat/start")
async def start_research(req: ChatRequest):
    """
    Starts the agent, runs the planner, and stops before execution.
    Returns the thread_id and the proposed plan.
    """
    # Generate a unique session ID if one isn't provided
    thread_id = req.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    set_thread_id(thread_id)

    # Start the graph. It will run 'planner' then INTERRUPT.
    # Note: We use iteration_count=0 to initialize our loop counter.
    initial_state = {
        "user_input": req.message,
        "plan": [],
        "results": [],
        "iteration_count": 0
    }
    
    # Run the graph until it hits the interrupt_before=["human_approval"]
    try:
        graph.invoke(initial_state, config)
    finally:
        clear_thread_id()

    # Get the state to see what the Planner came up with
    current_state = graph.get_state(config)
    proposed_plan = current_state.values.get("plan", [])

    return {
        "thread_id": thread_id,
        "status": "Awaiting Approval",
        "proposed_plan": proposed_plan
    }

@app.post("/chat/approve")
async def approve_research(req: ApprovalRequest):

    config = {"configurable": {"thread_id": req.thread_id}}

    current_state = graph.get_state(config)
    if not current_state.values:
        raise HTTPException(status_code=404, detail="Session not found")

    if not req.approve:
        return {"status": "cancelled"}

    # if human edited plan
    if req.edited_plan:
        graph.update_state(config, {"plan": req.edited_plan})

    set_thread_id(req.thread_id)

    # resume graph
    try:
        graph.invoke(None, config)
    finally:
        clear_thread_id()

    # get updated state
    new_state = graph.get_state(config)

    # 🔥 check where graph stopped
    next_node = new_state.next

    # ===============================
    # IF STOPPED AGAIN FOR APPROVAL
    # ===============================
    if next_node == ("human_approval",):
        proposed_plan = new_state.values.get("plan", [])

        return {
            "status": "awaiting_approval_again",
            "proposed_plan": proposed_plan
        }

    # ===============================
    # IF FINAL COMPLETE
    # ===============================
    final_answer = new_state.values.get("final_answer")

    return {
        "status": "complete",
        "final_answer": final_answer
    }
