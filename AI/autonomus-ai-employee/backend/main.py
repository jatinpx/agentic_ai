from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

from agent.planner import create_plan
from agent.executor import run_agent

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str

@app.get("/")
def home():
    return {"status": "AI Employee running"}

@app.post("/chat")
def chat(req: ChatRequest):

    user = req.message.lower()

    # -------- simple chat detection --------
    casual = ["hi", "hello", "hey", "how are", "what's up"]

    if any(c in user for c in casual) and len(user.split()) < 6:
        return {"response": run_agent(req.message)}

    # -------- memory info detection --------
    memory_words = ["my name is", "i am", "remember that"]

    if any(m in user for m in memory_words):
        return {"response": run_agent(req.message)}

    # -------- complex task → planner --------
    steps = create_plan(req.message)
    results = []

    if steps and len(steps) > 1:
        for step in steps:
            if isinstance(step, dict):
                step = list(step.values())[0]

            result = run_agent(step)
            results.append(result)

        return {"response": "\n".join(results)}

    return {"response": run_agent(req.message)}
