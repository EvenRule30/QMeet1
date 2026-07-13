from fastapi import APIRouter, HTTPException

from app.agent import AgentUserFacingError, interpret_command_intent
from app.schemas import CommandInterpretRequest, CommandInterpretResponse

router = APIRouter(prefix="/api/command", tags=["command"])


@router.post("/interpret", response_model=CommandInterpretResponse)
async def command_interpret(req: CommandInterpretRequest):
    message = req.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        intent = await interpret_command_intent(message)
        return CommandInterpretResponse(**intent)
    except AgentUserFacingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet command interpreter hit an unexpected error.",
        )
