from pydantic import BaseModel, Field
from typing import Any, Literal


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    state: Literal["idle", "listening", "thinking", "speaking", "error"] = "speaking"


class CommandInterpretRequest(BaseModel):
    message: str


class CommandInterpretResponse(BaseModel):
    intent: Literal["command", "chat"] = "chat"
    action: str = "none"
    confidence: float = 0.0
    frontendCommand: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
