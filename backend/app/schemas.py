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


class CalendarStatusResponse(BaseModel):
    ok: bool = True
    provider: Literal["google"] = "google"
    configured: bool = False
    connected: bool = False
    calendarId: str = "primary"
    writeEnabled: bool = False
    scope: str = ""
    message: str = ""


class CalendarAuthStartResponse(BaseModel):
    ok: bool = True
    authUrl: str = ""
    message: str = ""


class CalendarAuthResetResponse(BaseModel):
    ok: bool = True
    message: str = ""


class CalendarEventItem(BaseModel):
    id: str
    title: str
    dateKey: str
    time: str = "Later"
    createdAt: str
    source: Literal["local", "google"] = "google"
    googleEventId: str = ""
    start: str | None = None
    end: str | None = None
    location: str = ""
    description: str = ""
    allDay: bool = False
    calendarId: str = "primary"


class CalendarEventsResponse(BaseModel):
    ok: bool = True
    configured: bool = False
    connected: bool = False
    source: Literal["google"] = "google"
    view: Literal["today", "tomorrow", "week"] = "today"
    events: list[CalendarEventItem] = Field(default_factory=list)
    message: str = ""


class CalendarCreateEventRequest(BaseModel):
    title: str
    day: Literal["today", "tomorrow"] = "today"
    time: str = "Later"
    description: str = ""
    location: str = ""


class CalendarCreateEventResponse(BaseModel):
    ok: bool = True
    configured: bool = False
    connected: bool = False
    source: Literal["google"] = "google"
    event: CalendarEventItem | None = None
    message: str = ""
