from fastapi import APIRouter, HTTPException

from app.agent import AgentUserFacingError, search_web
from app.schemas import SearchRequest, SearchResponse
from app.work_context import (
    WorkContextError,
    record_background_search_failure,
    record_background_search_result,
)

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def web_search(req: SearchRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    try:
        raw_result = await search_web(query)
        response = SearchResponse(**raw_result)
        try:
            record_background_search_result(query, raw_result)
        except Exception:
            # Search must remain usable even if background context cannot be saved.
            pass
        return response
    except AgentUserFacingError as exc:
        try:
            record_background_search_failure(query, str(exc))
        except Exception:
            pass
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        try:
            record_background_search_failure(
                query,
                "QMeet web search hit an unexpected error.",
            )
        except Exception:
            pass
        raise HTTPException(
            status_code=500,
            detail="QMeet web search hit an unexpected error.",
        )
