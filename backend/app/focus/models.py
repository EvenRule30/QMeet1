from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FocusStatus(str, Enum):
    INACTIVE = "inactive"
    CLARIFYING = "clarifying"
    ACTIVE = "active"
    WAITING = "waiting"
    READY = "ready"
    COMPLETE = "complete"


class TurnRoute(str, Enum):
    RESPOND = "respond"
    TOOL = "tool"
    FOCUS_ACTION = "focus_action"
    CLARIFY = "clarify"
    NOOP = "noop"


class FocusOperationKind(str, Enum):
    START_FOCUS = "start_focus"
    RESCOPE_FOCUS = "rescope_focus"
    SET_FIELD = "set_field"
    ADD_LIST_ITEM = "add_list_item"
    REMOVE_LIST_ITEM = "remove_list_item"
    SET_PENDING_QUESTION = "set_pending_question"
    CLEAR_PENDING_QUESTION = "clear_pending_question"
    SET_PENDING_ACTION = "set_pending_action"
    CLEAR_PENDING_ACTION = "clear_pending_action"
    SET_NEXT_ACTION = "set_next_action"
    RECORD_PROGRESS = "record_progress"
    COMPLETE_MILESTONE = "complete_milestone"
    MARK_FOCUS_COMPLETE = "mark_focus_complete"
    END_FOCUS = "end_focus"


class FocusField(str, Enum):
    TITLE = "title"
    OBJECTIVE = "objective"
    DELIVERABLE = "deliverable"
    SUBJECT = "subject"
    STATUS = "status"
    NEXT_ACTION = "nextAction"
    STAKEHOLDERS = "stakeholders"
    REQUIREMENTS = "requirements"
    CONSTRAINTS = "constraints"
    PREFERENCES = "preferences"
    DECISIONS = "decisions"
    KNOWN_FACTS = "knownFacts"
    MILESTONES = "milestones"
    COMPLETED_MILESTONES = "completedMilestones"
    TAGS = "tags"


class ToolName(str, Enum):
    SEARCH = "search"
    CALENDAR_READ = "calendar_read"
    CALENDAR_WRITE = "calendar_write"
    VISUAL_READ = "visual_read"
    VISUAL_WRITE = "visual_write"
    OPEN_SEARCH = "open_search"
    START_FOCUS = "start_focus"
    END_FOCUS = "end_focus"
    SAVE_FOCUS_SUMMARY = "save_focus_summary"
    NONE = "none"


class ToolArgument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=80)
    value: str = Field(default="", max_length=1200)


class FocusOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: FocusOperationKind
    field: FocusField | None = None
    value: str = Field(default="", max_length=1600)
    values: list[str] = Field(default_factory=list, max_length=20)
    title: str = Field(default="", max_length=180)
    objective: str = Field(default="", max_length=500)
    target: str = Field(default="", max_length=80)
    question: str = Field(default="", max_length=320)
    tags: list[str] = Field(default_factory=list, max_length=12)
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=500)

    @field_validator("values", "tags")
    @classmethod
    def clean_string_lists(cls, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()

        for raw in values:
            item = " ".join(str(raw).split()).strip()
            key = item.casefold()
            if not item or key in seen:
                continue
            seen.add(key)
            result.append(item)

        return result


class PlannedToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool: ToolName
    arguments: list[ToolArgument] = Field(default_factory=list, max_length=20)
    reason: str = Field(default="", max_length=500)
    requiresConfirmation: bool = False
    attachToFocus: bool = False


class ResponseIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledge: str = Field(default="", max_length=400)
    answerDirectly: bool = True
    # Guarded visible-response takeover is allowed only when the planner
    # explicitly attaches this response to the durable current Focus.
    attachToFocus: bool = False
    # Direct guidance may contain a complete procedure or document-like answer.
    # The previous 1,200-character schema cap caused structured output to end
    # mid-sentence at exactly the limit.
    guidance: str = Field(default="", max_length=4000)
    askQuestion: str = Field(default="", max_length=320)


class TurnPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    route: TurnRoute = TurnRoute.RESPOND
    focusOperations: list[FocusOperation] = Field(default_factory=list, max_length=20)
    toolCalls: list[PlannedToolCall] = Field(default_factory=list, max_length=6)
    responseIntent: ResponseIntent = Field(default_factory=ResponseIntent)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=800)


class PendingQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target: str = Field(default="", max_length=80)
    question: str = Field(default="", max_length=320)
    askedAt: str = ""


class PendingAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=500)
    createdAt: str = ""


class FocusState(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    focusId: str = ""
    title: str = ""
    objective: str = ""
    deliverable: str = ""
    subject: str = ""
    stakeholders: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    knownFacts: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    completedMilestones: list[str] = Field(default_factory=list)
    pendingQuestion: PendingQuestion | None = None
    pendingAction: PendingAction | None = None
    nextAction: str = ""
    status: FocusStatus = FocusStatus.INACTIVE
    tags: list[str] = Field(default_factory=list)
    createdAt: str = ""
    updatedAt: str = ""
    lastTurnId: str = ""


class FocusEventType(str, Enum):
    LEGACY_IMPORTED = "legacy_imported"
    TURN_PLANNED = "turn_planned"
    RESPONSE_CANDIDATE = "response_candidate"
    ASSISTANT_REPLIED = "assistant_replied"
    RESPONSE_SELECTION = "response_selection"
    ROUTE_SELECTION = "route_selection"
    FOCUS_STARTED = "focus_started"
    FOCUS_RESCOPED = "focus_rescoped"
    FIELD_SET = "field_set"
    LIST_ITEM_ADDED = "list_item_added"
    LIST_ITEM_REMOVED = "list_item_removed"
    QUESTION_SET = "question_set"
    QUESTION_CLEARED = "question_cleared"
    ACTION_SET = "action_set"
    ACTION_CLEARED = "action_cleared"
    NEXT_ACTION_SET = "next_action_set"
    PROGRESS_RECORDED = "progress_recorded"
    MILESTONE_COMPLETED = "milestone_completed"
    TOOL_REQUESTED = "tool_requested"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    FOCUS_COMPLETED = "focus_completed"
    FOCUS_ENDED = "focus_ended"


class FocusEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    focusId: str = ""
    type: FocusEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    sourceTurnId: str = ""
    source: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    createdAt: str


class FocusEventLog(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: int = 1
    updatedAt: str = ""
    events: list[FocusEvent] = Field(default_factory=list)


class LegacyFocusSeed(BaseModel):
    model_config = ConfigDict(extra="ignore")

    focusId: str = ""
    title: str = ""
    objective: str = ""
    deliverable: str = ""
    subject: str = ""
    stakeholders: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    knownFacts: list[str] = Field(default_factory=list)
    milestones: list[str] = Field(default_factory=list)
    completedMilestones: list[str] = Field(default_factory=list)
    pendingQuestion: PendingQuestion | None = None
    nextAction: str = ""
    status: FocusStatus = FocusStatus.ACTIVE
    tags: list[str] = Field(default_factory=list)
    createdAt: str = ""
    updatedAt: str = ""


class PlanPreviewRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    source: str = Field(default="manual-preview", max_length=80)


class ObserveTurnRequest(BaseModel):
    message: str = Field(min_length=1, max_length=6000)
    source: str = Field(default="manual", max_length=80)
    apply: bool = True


class ToolResultRequest(BaseModel):
    tool: ToolName
    success: bool = True
    summary: str = Field(default="", max_length=2000)
    resultIds: list[str] = Field(default_factory=list, max_length=100)
    sourceTurnId: str = Field(default="", max_length=120)
