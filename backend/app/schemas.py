from typing import Any, Literal

from pydantic import BaseModel, Field


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


class CalendarUpdateEventRequest(BaseModel):
    title: str = ""
    day: Literal["today", "tomorrow"] | None = None
    time: str = ""
    description: str = ""
    location: str = ""


class CalendarUpdateEventResponse(BaseModel):
    ok: bool = True
    configured: bool = False
    connected: bool = False
    source: Literal["google"] = "google"
    event: CalendarEventItem | None = None
    message: str = ""


class CalendarDeleteEventResponse(BaseModel):
    ok: bool = True
    configured: bool = False
    connected: bool = False
    source: Literal["google"] = "google"
    deletedEventId: str = ""
    message: str = ""


MemorySessionMode = Literal["general", "coding", "meeting", "planning", "research", "personal"]


class MemoryTaskItem(BaseModel):
    id: str
    title: str
    createdAt: str
    completedAt: str | None = None


class MemoryNoteItem(BaseModel):
    id: str
    content: str
    createdAt: str


class RecentActionItem(BaseModel):
    id: str
    label: str
    detail: str = ""
    createdAt: str


class ActiveSessionItem(BaseModel):
    id: str
    title: str
    mode: MemorySessionMode = "general"
    goal: str = ""
    startedAt: str
    updatedAt: str
    pinnedNoteIds: list[str] = Field(default_factory=list)
    linkedTaskIds: list[str] = Field(default_factory=list)
    summary: str | None = None


class RecentFocusSessionItem(BaseModel):
    id: str
    title: str
    mode: MemorySessionMode = "general"
    goal: str = ""
    startedAt: str
    endedAt: str
    pinnedNoteIds: list[str] = Field(default_factory=list)
    linkedTaskIds: list[str] = Field(default_factory=list)
    summary: str | None = None
    summaryNoteId: str | None = None


class RecentFocusSessionsReplaceRequest(BaseModel):
    recentFocusSessions: list[RecentFocusSessionItem] = Field(default_factory=list)


class RecentFocusSessionsResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    recentFocusSessions: list[RecentFocusSessionItem] = Field(default_factory=list)
    message: str = ""


class RecentFocusSessionDeleteResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    deletedRecentFocusSessionId: str = ""
    message: str = ""


class RecentFocusSessionsClearResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    removedCount: int = 0
    recentFocusSessions: list[RecentFocusSessionItem] = Field(default_factory=list)
    message: str = ""


class ActiveSessionReplaceRequest(BaseModel):
    activeSession: ActiveSessionItem | None = None


class ActiveSessionUpdateRequest(BaseModel):
    title: str | None = None
    mode: MemorySessionMode | None = None
    goal: str | None = None
    pinnedNoteIds: list[str] | None = None
    linkedTaskIds: list[str] | None = None
    summary: str | None = None


class ActiveSessionResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    activeSession: ActiveSessionItem | None = None
    message: str = ""


class ActiveSessionClearResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    activeSession: ActiveSessionItem | None = None
    recentFocusSessions: list[RecentFocusSessionItem] = Field(default_factory=list)
    archivedFocusSession: RecentFocusSessionItem | None = None
    removedActiveSession: bool = False
    message: str = ""


class MemoryStatusResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    configured: bool = True
    path: str = ""
    taskCount: int = 0
    completedCount: int = 0
    actionCount: int = 0
    noteCount: int = 0
    activeSessionSet: bool = False
    activeSessionTitle: str = ""
    recentFocusSessionCount: int = 0
    lastFocusSessionTitle: str = ""
    message: str = ""


class MemoryTaskCreateRequest(BaseModel):
    title: str


class MemoryTaskUpdateRequest(BaseModel):
    title: str = ""
    completedAt: str | None = None


class MemoryTasksReplaceRequest(BaseModel):
    tasks: list[MemoryTaskItem] = Field(default_factory=list)


class MemoryTasksResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    tasks: list[MemoryTaskItem] = Field(default_factory=list)
    message: str = ""


class MemoryTaskDeleteResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    deletedTaskId: str = ""
    message: str = ""


class MemoryClearCompletedResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    removedCount: int = 0
    tasks: list[MemoryTaskItem] = Field(default_factory=list)
    message: str = ""


class MemoryContextReplaceRequest(BaseModel):
    tasks: list[MemoryTaskItem] = Field(default_factory=list)
    recentActions: list[RecentActionItem] = Field(default_factory=list)
    notes: list[MemoryNoteItem] = Field(default_factory=list)
    activeSession: ActiveSessionItem | None = None
    recentFocusSessions: list[RecentFocusSessionItem] = Field(default_factory=list)


class MemoryContextResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    tasks: list[MemoryTaskItem] = Field(default_factory=list)
    recentActions: list[RecentActionItem] = Field(default_factory=list)
    notes: list[MemoryNoteItem] = Field(default_factory=list)
    activeSession: ActiveSessionItem | None = None
    recentFocusSessions: list[RecentFocusSessionItem] = Field(default_factory=list)
    message: str = ""


class MemoryContextClearResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    tasks: list[MemoryTaskItem] = Field(default_factory=list)
    recentActions: list[RecentActionItem] = Field(default_factory=list)
    notes: list[MemoryNoteItem] = Field(default_factory=list)
    activeSession: ActiveSessionItem | None = None
    recentFocusSessions: list[RecentFocusSessionItem] = Field(default_factory=list)
    removedTaskCount: int = 0
    removedActionCount: int = 0
    removedNoteCount: int = 0
    removedActiveSession: bool = False
    removedRecentFocusSessionCount: int = 0
    message: str = ""


class MemoryContextExportResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    version: int = 6
    exportedAt: str = ""
    tasks: list[MemoryTaskItem] = Field(default_factory=list)
    recentActions: list[RecentActionItem] = Field(default_factory=list)
    notes: list[MemoryNoteItem] = Field(default_factory=list)
    activeSession: ActiveSessionItem | None = None
    recentFocusSessions: list[RecentFocusSessionItem] = Field(default_factory=list)
    message: str = ""


class MemoryContextImportRequest(BaseModel):
    tasks: list[MemoryTaskItem] = Field(default_factory=list)
    recentActions: list[RecentActionItem] = Field(default_factory=list)
    notes: list[MemoryNoteItem] = Field(default_factory=list)
    activeSession: ActiveSessionItem | None = None
    recentFocusSessions: list[RecentFocusSessionItem] = Field(default_factory=list)


class RecentActionCreateRequest(BaseModel):
    label: str
    detail: str = ""


class RecentActionsReplaceRequest(BaseModel):
    recentActions: list[RecentActionItem] = Field(default_factory=list)


class RecentActionsResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    recentActions: list[RecentActionItem] = Field(default_factory=list)
    message: str = ""


class RecentActionDeleteResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    deletedActionId: str = ""
    message: str = ""


class RecentActionsClearResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    removedCount: int = 0
    recentActions: list[RecentActionItem] = Field(default_factory=list)
    message: str = ""


class MemoryNoteCreateRequest(BaseModel):
    content: str


class MemoryNotesReplaceRequest(BaseModel):
    notes: list[MemoryNoteItem] = Field(default_factory=list)


class MemoryNotesResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    notes: list[MemoryNoteItem] = Field(default_factory=list)
    message: str = ""


class MemoryNoteDeleteResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    deletedNoteId: str = ""
    message: str = ""


class MemoryNotesClearResponse(BaseModel):
    ok: bool = True
    provider: Literal["local-json"] = "local-json"
    removedCount: int = 0
    notes: list[MemoryNoteItem] = Field(default_factory=list)
    message: str = ""


class SearchRequest(BaseModel):
    query: str


class SearchSourceItem(BaseModel):
    title: str = ""
    url: str = ""
    domain: str = ""
    usedFor: str = ""


class SearchResultCard(BaseModel):
    title: str = ""
    detail: str = ""


class SearchResponse(BaseModel):
    ok: bool = True
    query: str = ""
    summary: str = ""
    recommendation: str = ""
    steps: list[str] = Field(default_factory=list)
    cards: list[SearchResultCard] = Field(default_factory=list)
    sources: list[SearchSourceItem] = Field(default_factory=list)
    provider: str = ""
    message: str = ""
