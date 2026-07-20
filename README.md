# QMeet

QMeet is a voice-first AI tablet interface for the Chascii orb prototype. The frontend is a React/Vite app built around an interactive orb UI, and the backend is a FastAPI service for chat, command interpretation, web search, Google Calendar actions, visual analysis, and persistent memory.

The current prototype target is a 1024x600 Raspberry Pi/tablet-style screen. Laptop development remains normal browser development, while Raspberry Pi kiosk behavior lives in the launcher script and Pi documentation.

## Current status

QMeet currently supports:

- Text and browser voice input
- Spoken responses through browser speech synthesis
- OpenAI-backed chat streaming
- Immediate orb feedback while spoken prompts are routed
- Local exact command routing before normal chat
- Backend fuzzy command interpretation for natural phrasing
- Command/result toast cards
- Web search result cards
- Notes
- Backend-backed persistent memory for tasks, notes, recent actions, active focus sessions, recent focus history, and visual context
- Memory import/export/reset controls
- Google Calendar read/create/edit/delete with confirmation gates
- Active Context / Focus Sessions
- Focus-aware chat context
- Focus-to-tasks generation
- Focus summaries saved as notes
- Recent focus history, recall, resume, and local/enhanced recaps
- Focus nudges and clickable focus actions in the Memory panel
- Manual visual observations
- Browser camera preview and one-shot snapshots
- Snapshot/image analysis through the backend and OpenAI vision
- Visual observations stored as text context, not raw images
- Visual context included in chat
- Visual observations linked to active focus
- Image upload for visual analysis with compact no-preview upload UI
- Discreet chat-log toggle without starting voice input
- 1024x600 tablet/kiosk layout polish
- Raspberry Pi Chromium kiosk launcher in `scripts/pi-kiosk-start.sh`

## Phase status

```text
Phase 1   Browser speech input
Phase 2   Local UI commands
Phase 3   Browser speech output
Phase 4   Notes, local tools, settings
Phase 5   Fuzzy command interpreter and confirmations
Phase 6   Google Calendar read/create/delete/edit
Phase 7   Web search and result cards
Phase 8   Orb activity UI, tablet/kiosk polish, Pi launcher, docs cleanup
Phase 9   Local memory/task persistence and frontend refactor work
Phase 10  Backend-backed persistent memory
Phase 11  Regression audit and bug-fix hardening
Phase 12  Active Context / Focus Sessions
Phase 13  Workflow memory, focus nudges, history, and recaps
Phase 14  Visual context, manual observations, one-shot camera analysis
Phase 15  Visual-focus fusion, image upload, camera/chat UI polish
```

Phase 12 introduced the active context layer so QMeet can understand the user's current work mode, focus title, goal, linked tasks, and session state.

Phase 13 built workflow memory on that layer: proactive nudges, clickable focus actions, end-of-focus guardrails, recent focus history, focus recall/resume commands, deterministic local recaps, and LLM-enhanced progress recaps.

Phase 14 added visual context: manual visual notes, camera snapshots, backend image analysis, text-only visual observations, visual chat context, and camera/visual commands.

Phase 15 began fusing vision with focus and smoothing the UI: visual observations can link to the active focus, uploaded images can be analyzed without storing raw files, and the chat log can be opened discreetly without pressing the orb or starting voice input.

## Requirements

- Node.js 20+ recommended
- Python 3.11+ recommended
- OpenAI API key
- Google Calendar OAuth credentials, optional but needed for real calendar actions
- Browser camera permission, optional but needed for camera preview/snapshot analysis

## Run locally

### 1. Backend

From the repo root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `backend/.env`:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MAX_OUTPUT_TOKENS=300
OPENAI_VISION_MODEL=gpt-4.1-mini
QMEET_MAX_SNAPSHOT_BYTES=6291456
FRONTEND_ORIGIN=http://localhost:5173
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CALENDAR_WRITE_ENABLED=true
GOOGLE_CALENDAR_CREDENTIALS_FILE=google_credentials.json
GOOGLE_CALENDAR_TOKEN_FILE=token_calendar_events.json
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8000/api/calendar/auth/callback
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=local
```

Start the backend:

```powershell
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

Open a second terminal from the repo root:

```powershell
npm install
```

Create `.env.local`:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

Start the frontend:

```powershell
npm run dev -- --host 0.0.0.0
```

Open the Vite URL, usually:

```text
http://localhost:5173
```

## Test commands

Build and backend checks:

```powershell
npm run build
Invoke-RestMethod http://localhost:8000/api/status
Invoke-RestMethod http://localhost:8000/api/calendar/status
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=today"
Invoke-RestMethod http://localhost:8000/api/memory/status
Invoke-RestMethod http://localhost:8000/api/memory/context
Invoke-RestMethod http://localhost:8000/api/memory/sessions/recent
Invoke-RestMethod http://localhost:8000/api/memory/visual
```

Focus/session prompts:

```text
start a coding focus session for QMeet Phase 15
set my goal to test visual focus fusion
what is my current focus
turn this focus into tasks
save this focus as a note
end with summary
what was my last focus
resume my last focus
summarize what I worked on today
give me a better recap of today
what should I focus on next
```

Visual/camera prompts and actions:

```text
open camera
take snapshot
Analyze Snapshot
what was the last thing you saw
show visual observations
summarize visual context
save this visual context to my focus
show visuals for my focus
clear visual context
```

Image upload is available from the camera overlay. Uploaded images are analyzed from the original file blob. QMeet intentionally uses a compact metadata/no-preview upload UI because embedded browser previews showed inconsistent blur artifacts on some images.

## Privacy model for visual analysis

QMeet stores text observations, not raw images.

```text
Camera preview: local browser stream only
Snapshot before analysis: in-memory only
Analyze Snapshot: sends the current image to the backend, which sends it to OpenAI vision when configured
Saved memory: returned text description only
Uploaded images: analyzed from original file blob; raw file is not stored by QMeet
```

OpenAI API inputs are transmitted to OpenAI for analysis. API data is not used for model training by default, but may be temporarily retained under OpenAI's API data-retention policy depending on account settings.

## Raspberry Pi kiosk mode

Laptop development is unchanged. The Pi kiosk setup is separate and documented in:

```text
docs/pi-kiosk.md
scripts/pi-kiosk-start.sh
```

Basic Pi test:

```bash
chmod +x scripts/pi-kiosk-start.sh
QMEET_URL=http://YOUR_LAPTOP_IP:5173 ./scripts/pi-kiosk-start.sh
```

For Pi testing against a laptop-hosted backend, make sure the frontend `.env.local` uses the laptop LAN IP, not `localhost`:

```env
VITE_QMEET_API_URL=http://YOUR_LAPTOP_IP:8000
```

Restart Vite after changing `.env.local`.

## Persistent memory

QMeet's primary memory store is backend-local JSON:

```text
backend/data/qmeet_memory.json
```

It currently stores:

```text
tasks
notes
recentActions
activeSession
recentFocusSessions
visualContext
```

The frontend still keeps browser `localStorage` fallback copies so the UI can recover gracefully if the backend is unavailable. Backend memory is treated as primary after it has been initialized, including the case where backend memory is intentionally empty.

## Local browser storage

These browser-local keys are still used for fallback state and UI preferences:

```text
qmeet-notes
qmeet-calendar-events
qmeet-memory-tasks
qmeet-recent-actions
qmeet-active-session
qmeet-active-session-live
qmeet-recent-focus-sessions
qmeet-visual-context
qmeet-voice-output-enabled
qmeet-speech-rate
```

Clearing site data or switching browsers/devices can affect fallback state and preferences. Google Calendar OAuth tokens are backend-local files, not browser storage.

## Do not commit secrets

Keep these files local only:

```text
.env.local
backend/.env
backend/google_credentials.json
backend/token_calendar_readonly.json
backend/token_calendar_events.json
backend/calendar_auth_state.json
backend/data/qmeet_memory.json
```

## More docs

- `docs/development.md` - setup details, API endpoints, phase history, testing, troubleshooting
- `docs/architecture.md` - current frontend/backend architecture snapshot
- `docs/pi-kiosk.md` - Raspberry Pi kiosk launch/autostart notes

## Project structure

```text
repo root
├─ src/app/
│  ├─ App.tsx
│  ├─ api.ts
│  ├─ commands.ts
│  ├─ types.ts
│  ├─ camera/
│  │  └─ CameraCaptureOverlay.tsx
│  ├─ components/
│  │  ├─ ChatLogToggle.tsx
│  │  └─ ...
│  ├─ commandHandlers/
│  │  ├─ calendar.ts
│  │  ├─ memory.ts
│  │  ├─ notes.ts
│  │  ├─ search.ts
│  │  └─ voice.ts
│  ├─ hooks/
│  ├─ lib/
│  └─ panels/
├─ backend/app/
│  ├─ main.py
│  ├─ agent.py
│  ├─ calendar_service.py
│  ├─ memory_store.py
│  ├─ schemas.py
│  └─ routers/
│     ├─ calendar.py
│     ├─ chat.py
│     ├─ command.py
│     ├─ memory.py
│     ├─ memory_state.py
│     ├─ search.py
│     └─ visual.py
├─ docs/
├─ guidelines/
└─ scripts/
```
