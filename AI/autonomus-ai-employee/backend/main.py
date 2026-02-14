from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from brain.graph import build_graph
from agent.planner import create_plan
from agent.executor import run_agent

app = FastAPI()
graph = build_graph()

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

    result = graph.invoke({
        "user_input": req.message,
        "plan": [],
        "results": [],
        "final_answer": ""
    })

    return {"response": result["final_answer"]}

