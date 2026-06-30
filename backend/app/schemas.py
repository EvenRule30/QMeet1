from pydantic import BaseModel
from typing import Literal


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    state: Literal["idle", "listening", "thinking", "speaking", "error"] = "speaking"