from fastapi import APIRouter

from app.calendar_read_date_interpreter import (
    apply_calendar_absolute_create_ownership_floor,
    apply_calendar_absolute_edit_delete_ownership_floor,
    apply_calendar_range_read_ownership_floor,
)
from app.daily_brief_ownership import apply_daily_brief_ownership_floor
from app.focus_proposal_ownership import apply_focus_proposal_ownership_floor
from app.qmeet_agent_shadow import (
    AgentShadowRequest,
    AgentShadowResponse,
    decide_agent_shadow,
    shadow_status,
)
from app.qmeet_device_ui_ownership import apply_device_ui_ownership_floor
from app.qmeet_agent_composite import AgentCompositePlanResponse, plan_agent_composite

router = APIRouter(prefix="/api/agent/shadow", tags=["agent-shadow"])


@router.get("/status")
async def status():
    return shadow_status()


@router.post("/decide", response_model=AgentShadowResponse)
async def decide(req: AgentShadowRequest):
    """Return unified-agent semantics; deterministic capability gates execute later."""

    response = await decide_agent_shadow(req)

    repaired_decision = apply_device_ui_ownership_floor(
        req.userMessage,
        response.decision,
    )

    repaired_decision = apply_calendar_absolute_create_ownership_floor(
        req.userMessage,
        repaired_decision,
    )
    repaired_decision = apply_calendar_absolute_edit_delete_ownership_floor(
        req.userMessage,
        repaired_decision,
    )

    repaired_decision = apply_calendar_range_read_ownership_floor(
        req.userMessage,
        repaired_decision,
    )

    # Phase 21I1B: broad day-planning language is intentionally cross-capability.
    # Apply this after the ordinary single-capability repair floors so an
    # over-eager Tasks/Calendar proposal cannot collapse Daily Brief to one read.
    repaired_decision = apply_daily_brief_ownership_floor(
        req.userMessage,
        repaired_decision,
    )

    # Phase 21I4: a fresh one-turn acceptance of QMeet's own Daily Brief
    # proposal stays Focus-owned. Any unrelated next turn expires that proposal.
    repaired_decision = apply_focus_proposal_ownership_floor(
        req.userMessage,
        repaired_decision,
    )

    if repaired_decision is response.decision:
        return response

    return response.model_copy(update={"decision": repaired_decision})


@router.post("/plan", response_model=AgentCompositePlanResponse)
async def plan_composite(req: AgentShadowRequest):
    """Phase 21G1 observational composite plan; never executes plan steps."""

    return await plan_agent_composite(req)
