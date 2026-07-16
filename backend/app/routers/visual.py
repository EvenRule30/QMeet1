import base64
import os
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

try:
    from openai import AsyncOpenAI
except Exception:  # pragma: no cover - handled at runtime when OpenAI is unavailable
    AsyncOpenAI = None  # type: ignore[assignment]


router = APIRouter(prefix="/api/visual", tags=["visual"])

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
MAX_SNAPSHOT_BYTES = int(os.getenv("QMEET_MAX_SNAPSHOT_BYTES", str(6 * 1024 * 1024)))
DEFAULT_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"


class SnapshotAnalysisResponse(BaseModel):
    ok: bool
    source: Literal["camera"] = "camera"
    summary: str
    model: str
    contentType: str
    imageBytesReceived: int
    confidence: Optional[float] = None


def _clean_content_type(value: str | None) -> str:
    if not value:
        return "application/octet-stream"
    return value.split(";", 1)[0].strip().lower()


def _is_openai_enabled() -> bool:
    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()
    return provider in {"openai", "openai-compatible", "openai_compatible"}


def _mock_summary(image_bytes: bytes, content_type: str) -> SnapshotAnalysisResponse:
    return SnapshotAnalysisResponse(
        ok=True,
        summary=(
            "Camera snapshot received, but vision analysis is running in mock mode. "
            "Configure LLM_PROVIDER=openai and OPENAI_API_KEY to generate real visual observations."
        ),
        model="mock-vision",
        contentType=content_type,
        imageBytesReceived=len(image_bytes),
        confidence=None,
    )


def _extract_response_text(response: object) -> str:
    output_text = getattr(response, "output_text", None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    choices = getattr(response, "choices", None)
    if choices:
        first_choice = choices[0]
        message = getattr(first_choice, "message", None)
        content = getattr(message, "content", None)
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                text = getattr(item, "text", None)
                if isinstance(text, str):
                    parts.append(text)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            joined = " ".join(part.strip() for part in parts if part.strip())
            if joined:
                return joined

    return "I could not extract a visual observation from the model response."


@router.post("/analyze-snapshot", response_model=SnapshotAnalysisResponse)
async def analyze_snapshot(request: Request) -> SnapshotAnalysisResponse:
    """Analyze a single camera snapshot without storing the raw image.

    The request body should be raw image bytes with one of these content types:
    image/jpeg, image/png, or image/webp. The response is a short textual
    observation that the frontend can decide whether to save into visualContext.
    """

    content_type = _clean_content_type(request.headers.get("content-type"))
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Snapshot must be sent as image/jpeg, image/png, or image/webp.",
        )

    image_bytes = await request.body()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Snapshot image is empty.")

    if len(image_bytes) > MAX_SNAPSHOT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Snapshot is too large. Max size is {MAX_SNAPSHOT_BYTES} bytes.",
        )

    if not _is_openai_enabled():
        return _mock_summary(image_bytes, content_type)

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _mock_summary(image_bytes, content_type)

    if AsyncOpenAI is None:
        raise HTTPException(
            status_code=503,
            detail="OpenAI client is not available in the backend environment.",
        )

    data_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    model = DEFAULT_VISION_MODEL

    try:
        client = AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model=model,
            max_tokens=180,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are QMeet's visual context observer. Describe the useful, visible context "
                        "from this camera snapshot in 1-3 concise sentences. Focus on objects, text, "
                        "workspace state, and anything relevant to the user's current task. Do not identify "
                        "private individuals or speculate beyond what is visible."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Create a short visual observation from this snapshot. Return only the "
                                "observation text, with no markdown heading."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                            },
                        },
                    ],
                },
            ],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Vision analysis failed: {exc}",
        ) from exc

    summary = _extract_response_text(response).strip()
    if not summary:
        raise HTTPException(status_code=502, detail="Vision model returned an empty observation.")

    return SnapshotAnalysisResponse(
        ok=True,
        summary=summary,
        model=model,
        contentType=content_type,
        imageBytesReceived=len(image_bytes),
        confidence=None,
    )
