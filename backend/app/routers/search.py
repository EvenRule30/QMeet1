from fastapi import APIRouter, HTTPException

from app.agent import AgentUserFacingError, search_web
from app.schemas import SearchRequest, SearchResponse

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def web_search(req: SearchRequest):
    query = req.query.strip()

    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    try:
        return SearchResponse(**await search_web(query))
    except AgentUserFacingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="QMeet web search hit an unexpected error.",
        )
