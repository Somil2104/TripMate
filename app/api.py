from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Any, Dict
from graph.supervisor import build_supervisor

app = FastAPI(title="TripMate Agents API", version="0.1.0")

# Create a singleton compiled app (in-memory checkpointer in future step)
SUPERVISOR_APP = build_supervisor()


class ChatRequest(BaseModel):
    session_id: str
    message: str
    state: Dict[str, Any] | None = None  # client may include known state (optional)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    # Merge a minimal state; in later steps, load and persist by session_id
    state = req.state or {}
    state.setdefault("session_id", req.session_id)
    msgs = state.get("messages", [])
    msgs.append({"role": "user", "content": req.message})
    state["messages"] = msgs

    try:
        out = SUPERVISOR_APP.invoke(state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"state": out}


@app.get("/session/{session_id}")
def get_session(session_id: str):
    # Placeholder: in next step, read from checkpointer or DB/cache by session_id
    return {"session_id": session_id, "state": None}


class ApprovalRequest(BaseModel):
    session_id: str
    field: str = "granted"
    value: bool = True


@app.post("/approve")
def approve(req: ApprovalRequest):
    # Placeholder: accept approval and return ack; in next step, persist and resume flow
    return {"ok": True, "session_id": req.session_id, "applied": {req.field: req.value}}
