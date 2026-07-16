# QMeet

QMeet is a voice-first AI tablet interface for the Chascii orb prototype. The frontend is a React/Vite app built around an interactive orb UI, and the backend is a FastAPI service for chat, command interpretation, web search, Google Calendar actions, and persistent memory.

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
- Backend-backed persistent memory for tasks, notes, recent actions, active focus sessions, and recent focus history
- Memory import/export/reset controls
- Google Calendar read/create/edit/delete with confirmation gates
- Active Context / Focus Sessions
- Focus-aware chat context
- Focus-to-tasks generation
- Focus summaries saved as notes
- Recent focus history, recall, resume, and local/enhanced recaps
- Focus nudges and clickable focus actions in the Memory panel
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
```

Phase 12 introduced the active context layer so QMeet can understand the user's current work mode, focus title, goal, linked tasks, and session state.

Phase 13 builds on that layer with workflow memory: proactive nudges, clickable focus actions, end-of-focus guardrails, recent focus history, focus recall/resume commands, deterministic local recaps, and LLM-enhanced progress recaps.

Future camera/video support should plug into this context layer as another perception source instead of being built as an isolated webcam feature.

## Requirements

- Node.js 20+ recommended
- Python 3.11+ recommended
- OpenAI API key
- Google Calendar OAuth credentials, optional but needed for real calendar actions

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
```

Useful QMeet prompts:

```text
open menu
note that test the tablet UI
read my notes
open memory
remember to test the Pi kiosk as a task
what was I working on
mark task done
search for raspberry pi chromium kiosk mode
what's on my calendar tomorrow
add event tomorrow at 3 called project sync
delete the 12:00 PM event tomorrow
go home
```

Focus/session prompts:

```text
start a coding focus session for QMeet Phase 13
set my goal to test workflow memory
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
- `docs/phase-12-context-engine.md` - active context/focus-session design and implemented behavior
- `docs/phase-13-workflow-memory.md` - workflow memory, nudges, history, recaps, and regression checklist

## Project structure

```text
repo root
├─ src/app/
│  ├─ App.tsx
│  ├─ api.ts
│  ├─ commands.ts
│  ├─ types.ts
│  ├─ components/
│  ├─ commandHandlers/
│  │  ├─ calendar.ts
│  │  ├─ memory.ts
│  │  ├─ notes.ts
│  │  ├─ search.ts
│  │  └─ voice.ts
│  ├─ hooks/
│  │  ├─ useBackendStatus.ts
│  │  ├─ useCalendarController.ts
│  │  ├─ useChatStreamController.ts
│  │  ├─ useMemoryContext.ts
│  │  ├─ useResultToasts.ts
│  │  ├─ useSearchController.ts
│  │  ├─ useSpeechOutput.ts
│  │  └─ useSpeechRecognitionController.ts
│  ├─ lib/
│  │  ├─ activityUtils.ts
│  │  ├─ calendarUtils.ts
│  │  ├─ chatFlowUtils.ts
│  │  ├─ commandRouterUtils.ts
│  │  ├─ dateUtils.ts
│  │  ├─ memoryUtils.ts
│  │  └─ toastUtils.ts
│  └─ panels/
│     ├─ CalendarOverlay.tsx
│     ├─ MemoryOverlay.tsx
│     ├─ MenuOverlay.tsx
│     ├─ NotesOverlay.tsx
│     ├─ SearchOverlay.tsx
│     ├─ SettingsOverlay.tsx
│     └─ StatusOverlay.tsx
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
│     └─ search.py
├─ docs/
├─ guidelines/
└─ scripts/
```
