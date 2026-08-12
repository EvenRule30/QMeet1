# QMeet

QMeet is a voice-first AI tablet interface built around the Chascii orb concept. The current prototype combines a React/Vite tablet UI with a FastAPI backend for AI chat, command routing, Google Calendar, persistent memory, visual context, and Active Focus.

The main hardware target is a 1024x600 Raspberry Pi/tablet-style display, but normal development runs in a desktop browser.

## What QMeet can do

Current prototype capabilities include:

- Text and browser voice input
- Browser speech synthesis for spoken replies
- OpenAI-backed chat and streaming responses
- Exact local commands plus model-assisted intent routing
- Google Calendar read/create/edit/delete flows
- Tasks, notes, recent actions, and persistent memory
- Active Focus sessions with goals, context, tasks, summaries, history, resume, and progress tracking
- Focus-aware coaching and meeting preparation
- Web search
- Camera snapshots and uploaded-image analysis
- Saved visual observations that can be linked to a Focus
- Orb/tablet UI with Memory, Calendar, Search, Notes, Camera, Settings, and status panels
- Raspberry Pi Chromium kiosk launch support

QMeet is still a prototype. Some routing and coaching paths are transitional while the project moves toward a more unified agent architecture.

## Requirements

- Node.js 20+ recommended
- Python 3.11+ recommended
- An OpenAI API key for real AI behavior
- Google Calendar OAuth credentials only if you want connected calendar actions
- Chrome or another browser with microphone/camera support for voice and camera features

## Run locally

### 1. Backend

From the repository root:

#### Windows PowerShell

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

#### Linux/macOS

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

For real OpenAI responses, edit `backend/.env` and set at minimum:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4.1-mini
FRONTEND_ORIGIN=http://localhost:5173
```

The repository's `.env.example` defaults to mock mode, so it is safe to start without an API key while checking the app itself.

Start FastAPI:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend health check:

```text
http://localhost:8000/health
```

### 2. Frontend

Open a second terminal at the repository root:

```powershell
npm install
```

Create `.env.local`:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

Start Vite:

```powershell
npm run dev -- --host 0.0.0.0
```

Open the displayed Vite URL, normally:

```text
http://localhost:5173
```

## Google Calendar setup

Calendar integration is optional. Without Google credentials, the rest of QMeet can still run.

When using Google Calendar, place the OAuth client credentials file in `backend/` and configure `backend/.env` similar to:

```env
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CALENDAR_WRITE_ENABLED=true
GOOGLE_CALENDAR_CREDENTIALS_FILE=google_credentials.json
GOOGLE_CALENDAR_TOKEN_FILE=token_calendar_events.json
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8000/api/calendar/auth/callback
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=local
```

The token and auth-state files are generated locally during authorization.

## High-level architecture

```text
User
  |
  v
React / Vite tablet UI
  |- Orb, chat, panels, voice and camera UI
  |- Exact local command parser
  |- Command handlers and confirmation gates
  |- Typed FastAPI client
  |
  v
FastAPI backend
  |- QMeet intent orchestrator
  |- Normal AI chat / streaming
  |- Canonical Active Focus system
  |- Persistent memory
  |- Google Calendar
  |- Search
  |- Vision / snapshot analysis
  |
  +--> OpenAI API
  +--> Google Calendar API
```

QMeet currently uses a **hybrid command + chat architecture**. It is not yet a single general-purpose agent.

For a user message, the system can:

1. Match a known local command directly.
2. Ask the backend intent orchestrator whether the message maps to a supported QMeet action.
3. Execute the selected deterministic frontend/backend tool path.
4. Fall back to normal conversational chat when no tool action should own the turn.

`backend/app/qmeet_orchestrator.py` is intentionally a thin router. It chooses between known QMeet capabilities and normal chat; the existing deterministic command/tool implementations still perform the actual action.

## Active Focus architecture

Active Focus is the most developed stateful workflow in QMeet.

```text
User Focus turn
  |
  v
Focus routing / semantic interpretation
  |
  v
Verified native operation
  |- start
  |- update
  |- add context
  |- create/link tasks
  |- save summary
  |- end / complete
  |- resume
  |
  v
Canonical Focus event log
  |
  v
Reduced current Focus state
  |
  +--> UI / Memory panel
  +--> coaching context
  +--> task progress
  +--> summaries / history
```

The canonical Focus event log lives at:

```text
backend/data/qmeet_focus.json
```

or at the path specified by `QMEET_FOCUS_FILE`.

Important Focus code is under:

```text
backend/app/focus/
```

Key responsibilities include:

- `store.py` - event log, state reduction, guarded routing/response telemetry
- `models.py` - canonical Focus models and event types
- `lifecycle.py` - verified start/update/end/resume operations
- `context.py` - verified durable Focus context writes
- `context_boundary.py` - decides which natural-language details belong to Focus context
- `context_hygiene.py` - deduplication, corrections, and coaching-question answer checks
- `tasks.py`, `task_progress.py`, `task_lineage.py` - Focus-linked task behavior
- `summary.py` - Focus summary persistence
- `calendar_prep.py` - calendar-to-Focus preparation
- `planner.py` - Focus turn planning/coaching
- `middleware.py` and `native_read_middleware.py` - guarded Focus routing/read behavior

### Canonical Focus versus legacy Memory

Older QMeet versions stored an active session inside the general Memory document. The current Focus system uses the canonical event store as runtime authority.

`backend/app/focus/canonical_work_context_source.py` adapts canonical Focus state into the older background-coaching seam. This prevents stale compatibility Memory data from becoming an active Focus again after a canonical Focus has ended.

Legacy Focus bootstrap is intentionally disabled during normal runtime. `QMEET_ENABLE_LEGACY_FOCUS_BOOTSTRAP=1` is only for an explicit migration/bootstrap operation and should not be enabled for normal use.

## General memory

QMeet still uses the backend memory store for non-Focus data such as tasks, notes, recent actions, and visual observations.

The prototype-local memory file is:

```text
backend/data/qmeet_memory.json
```

Browser storage is used as fallback/migration support, but backend state is intended to be authoritative after initialization.

## Normal chat and coaching

Normal chat is handled through the FastAPI chat routes and `backend/app/agent.py`. Background workflow context can be added to the conversation through `work_context.py` and its middleware.

The current codebase therefore has several reasoning layers:

```text
frontend command routing
backend intent orchestrator
normal chat agent
Focus planner / semantic routing
background work-context coaching
```

This separation is useful for the prototype but is also the main architectural area currently being simplified. The planned direction is a unified QMeet agent that can reason across general chat, Calendar, Memory, Focus, Search, and other tools while keeping deterministic backend verification for state-changing operations.

A future agent should **not** assume every message belongs to an active Focus. For example, a general question or a request to add a calendar event should remain general chat/calendar work unless the user clearly connects it to the Focus.

## Main project structure

```text
repo root
|- src/app/
|  |- App.tsx                 # top-level tablet/orb orchestration
|  |- api.ts                  # FastAPI client and streaming helpers
|  |- commands.ts             # exact local command parser
|  |- commandHandlers/        # feature command execution
|  |- hooks/                  # chat, memory, calendar, search, speech state
|  |- panels/                 # Memory, Calendar, Search, Settings, etc.
|  |- camera/                 # browser camera/snapshot UI
|  `- components/             # reusable UI pieces
|
|- backend/app/
|  |- main.py                 # FastAPI app, middleware, router registration
|  |- agent.py                # normal AI chat/streaming helpers
|  |- qmeet_orchestrator.py   # thin intent/action router
|  |- qmeet_capabilities.py   # supported orchestrator action catalog
|  |- work_context.py         # background workflow/coaching compatibility layer
|  |- memory_store.py         # general persistent memory
|  |- calendar_service.py     # Google Calendar OAuth/API
|  |- focus/                  # canonical Active Focus implementation
|  `- routers/                # HTTP API routes
|
|- backend/tests/             # backend regression suite
|- docs/                      # development, architecture, Pi notes
|- scripts/                   # kiosk/startup helpers
`- package.json
```

## Tests

From `backend/` with the virtual environment active:

```powershell
python -m unittest discover -s tests -v
```

Frontend production build:

```powershell
npm run build
```

Useful backend checks:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/status
Invoke-RestMethod http://localhost:8000/api/calendar/status
Invoke-RestMethod http://localhost:8000/api/memory/status
```

The Focus system has a large regression suite under `backend/tests/test_focus*.py`. After modifying Focus lifecycle, routing, context, tasks, or planner behavior, run the Focus tests before the complete backend suite.

## Raspberry Pi / kiosk mode

Pi-specific notes live in:

```text
docs/pi-kiosk.md
scripts/pi-kiosk-start.sh
```

For a Pi using a backend hosted on another machine, the frontend must point at that machine's LAN IP rather than `localhost`:

```env
VITE_QMEET_API_URL=http://YOUR_LAPTOP_IP:8000
```

Example kiosk launch:

```bash
chmod +x scripts/pi-kiosk-start.sh
QMEET_URL=http://YOUR_LAPTOP_IP:5173 ./scripts/pi-kiosk-start.sh
```

## Do not commit secrets or local user data

Keep these local:

```text
.env.local
backend/.env
backend/google_credentials.json
backend/token_calendar_readonly.json
backend/token_calendar_events.json
backend/calendar_auth_state.json
backend/data/qmeet_memory.json
backend/data/qmeet_focus.json
```

Also avoid committing personal camera snapshots or uploaded test images unless they are intentional fixtures.

## More documentation

- `docs/development.md` - detailed development/setup notes and older workflow history
- `docs/architecture.md` - architecture snapshot; some sections may lag the newer canonical Focus work
- `docs/pi-kiosk.md` - Raspberry Pi kiosk setup

For new contributors, start with this README, then inspect `src/app/App.tsx`, `backend/app/main.py`, `backend/app/qmeet_orchestrator.py`, and `backend/app/focus/`.
