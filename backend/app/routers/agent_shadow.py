from fastapi import APIRouter, Query

from app.qmeet_agent_shadow import (
    AgentShadowCompareRequest,
    AgentShadowCompareResponse,
    AgentShadowRequest,
    AgentShadowResponse,
    compare_agent_shadow_turn,
    decide_agent_shadow,
    shadow_recent,
    shadow_status,
)


router = APIRouter(prefix="/api/agent/shadow", tags=["agent-shadow"])


@router.get("/status")
async def status():
    return shadow_status()


@router.get("/recent")
async def recent(
    limit: int = Query(default=20, ge=1, le=50),
    disagreements_only: bool = Query(default=False, alias="disagreementsOnly"),
):
    """Inspect recent shadow decisions paired with the latest observed legacy route."""
    return shadow_recent(limit=limit, disagreements_only=disagreements_only)


@router.post("/decide", response_model=AgentShadowResponse)
async def decide(req: AgentShadowRequest):
    """Phase 21B unified-agent decision in observational shadow mode only."""
    return await decide_agent_shadow(req)


@router.post("/compare", response_model=AgentShadowCompareResponse)
async def compare(req: AgentShadowCompareRequest):
    """Attach the authoritative legacy route observed after a shadow decision."""
    return compare_agent_shadow_turn(req)
