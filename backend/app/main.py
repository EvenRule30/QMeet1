import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from app.routers import (  # noqa: E402
    calendar,
    chat,
    command,
    memory,
    memory_state,
    search,
    visual,
)

app = FastAPI(title="QMeet Agent Backend")

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
