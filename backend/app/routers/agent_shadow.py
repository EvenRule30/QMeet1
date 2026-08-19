from fastapi import APIRouter

from app.qmeet_agent_shadow import (
    AgentShadowRequest,
    AgentShadowResponse,
    decide_agent_shadow,
    shadow_status,
)
from app.qmeet_device_ui_ownership import apply_device_ui_ownership_floor


router = APIRouter(prefix="/api/agent/shadow", tags=["agent-shadow"])


@router.get("/status")
async def status():
    return shadow_status()


@router.post("/decide", response_model=AgentShadowResponse)
async def decide(req: AgentShadowRequest):
    """Return the unified-agent decision; execution remains deterministic elsewhere."""

    response = await decide_agent_shadow(req)
    repaired_decision = apply_device_ui_ownership_floor(
        req.userMessage,
        response.decision,
    )
    if repaired_decision is response.decision:
        return response
    return response.model_copy(update={"decision": repaired_decision})
