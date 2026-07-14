from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.memory_store import MemoryStoreError, get_memory_status


router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("/initialization")
async def memory_initialization():
    """Report whether the backend memory file has ever been initialized.

    Empty arrays are valid saved state, so clients must not assume that an
    empty response means the backend has never stored memory.
    """

    try:
        status = get_memory_status()
        memory_path = Path(str(status.get("path") or ""))

        return {
            "ok": True,
            "initialized": bool(memory_path) and memory_path.exists(),
        }
    except MemoryStoreError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet could not determine memory initialization state.",
        )
