import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.background_context_middleware import BackgroundWorkContextMiddleware  # noqa: E402
from app.focus.middleware import FocusShadowMiddleware  # noqa: E402
from app.focus.native_read_middleware import (  # noqa: E402
    FocusNativeReadRouteMiddleware,
)
from app.routers import (  # noqa: E402
    calendar,
    chat,
    command,
    focus,
    memory,
    memory_state,
    search,
    visual,
)

app = FastAPI(title="QMeet Agent Backend")
# Middleware is registered inside-out. FocusShadowMiddleware remains outside the
# native read router so it still owns shared turn planning, guarded comparison,
# telemetry, and fallback. The native layer only replaces the downstream legacy
# command-model call for a conservative read-only allowlist.
app.add_middleware(BackgroundWorkContextMiddleware)
app.add_middleware(FocusNativeReadRouteMiddleware)
app.add_middleware(FocusShadowMiddleware)
frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
# For prototype LAN/tablet testing this stays permissive. Tighten this before
# a real deployment by switching allow_origins back to [frontend_origin].
app.add_middleware(
    CORSMiddleware,
    # allow_origins=[frontend_origin],
    allow_origins=["*"],
    # allow_credentials=True,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "ok": True,
        "service": "qmeet-agent",
    }


app.include_router(chat.router)
app.include_router(command.router)
app.include_router(search.router)
app.include_router(calendar.router)
app.include_router(memory.router)
app.include_router(memory_state.router)
app.include_router(visual.router)
app.include_router(focus.router)
