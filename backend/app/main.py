import os
from dotenv import load_dotenv

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.agent import (
    AgentUserFacingError,
    generate_reply,
    get_public_status,
)
from app.schemas import ChatRequest, ChatResponse

load_dotenv()

app = FastAPI(title="QMeet Agent Backend")

frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "qmeet-agent",
    }


@app.get("/api/status")
async def status():
    return get_public_status()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    message = req.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        reply = await generate_reply(message)
        return ChatResponse(reply=reply, state="speaking")
    except AgentUserFacingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet backend hit an unexpected error.",
        )