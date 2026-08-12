from fastapi import APIRouter

from app.qmeet_agent_shadow import (
    AgentShadowRequest,
    AgentShadowResponse,
    decide_agent_shadow,
    shadow_status,
)


router = APIRouter(prefix="/api/agent/shadow", tags=["agent-shadow"])


@router.get("/status")
async def status():
    return shadow_status()


@router.post("/decide", response_model=AgentShadowResponse)
async def decide(req: AgentShadowRequest):
    """Phase 21B unified-agent decision in observational shadow mode only."""
    return await decide_agent_shadow(req)
