from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.focus.semantic_update_intent import (
    BRIDGE_VERSION,
    SemanticUpdateIntent,
    get_semantic_focus_update_decision,
    looks_like_semantic_focus_update_request,
)


class SemanticFocusUpdatePreflightRequest(BaseModel):
    """Natural-language request that may update the current Focus."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=2000)
    sourceTurnId: str = Field(default="", max_length=120)

    @field_validator("message")
    @classmethod
    def clean_message(cls, value: str) -> str:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            raise ValueError("message cannot be blank")
        return cleaned

    @field_validator("sourceTurnId")
    @classmethod
    def clean_source_turn_id(cls, value: str) -> str:
        return " ".join(value.split()).strip()


class SemanticFocusUpdatePreflightResult(BaseModel):
    """Typed classification only; canonical mutation happens separately."""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    bridgeVersion: Literal["phase20d2a4c"] = BRIDGE_VERSION
    intent: Literal["update", "not_update", "clarify"]
    possibleUpdate: bool = False
    title: str = ""
    objective: str = ""
    objectiveSpecified: bool = False
    mode: Literal[
        "general",
        "coding",
        "meeting",
        "planning",
        "research",
        "personal",
    ] | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""
    message: str = ""
    sourceTurnId: str = ""


async def semantic_focus_update_preflight(
    request: SemanticFocusUpdatePreflightRequest,
) -> SemanticFocusUpdatePreflightResult:
    """Classify a possible current-Focus update without applying it.

    This endpoint intentionally lives under the lifecycle router, outside the
    guarded chat/command response path. It cannot emit planner success prose or
    write Focus events. The frontend converts an UPDATE result into the existing
    verified native /update call.
    """

    decision = await get_semantic_focus_update_decision(
        request.message,
        source_turn_id=request.sourceTurnId,
    )
    possible_update = (
        decision.intent != SemanticUpdateIntent.NOT_UPDATE
        or looks_like_semantic_focus_update_request(request.message)
    )

    if decision.intent == SemanticUpdateIntent.UPDATE:
        return SemanticFocusUpdatePreflightResult(
            intent="update",
            possibleUpdate=True,
            title=decision.title,
            objective=decision.objective,
            objectiveSpecified=decision.objectiveSpecified,
            mode=decision.mode,
            confidence=decision.confidence,
            reason=decision.reason,
            sourceTurnId=request.sourceTurnId,
        )

    if decision.intent == SemanticUpdateIntent.CLARIFY:
        return SemanticFocusUpdatePreflightResult(
            intent="clarify",
            possibleUpdate=True,
            confidence=decision.confidence,
            reason=decision.reason,
            message=(
                "I understood this as a possible Focus change, but I could "
                "not identify one specific title, goal, or mode update safely. "
                "The Focus was not changed."
            ),
            sourceTurnId=request.sourceTurnId,
        )

    return SemanticFocusUpdatePreflightResult(
        intent="not_update",
        possibleUpdate=possible_update,
        confidence=decision.confidence,
        reason=decision.reason,
        sourceTurnId=request.sourceTurnId,
    )
