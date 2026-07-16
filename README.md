# QMeet

QMeet is a voice-first AI tablet interface for the Chascii orb prototype. The frontend is a React/Vite app built around an interactive orb UI, and the backend is a FastAPI service for chat, command interpretation, web search, Google Calendar actions, and persistent memory.

The current project direction is an on-screen orb assistant for a future AI tablet. The user should be able to speak naturally, have QMeet route tool actions locally when possible, and keep enough memory/context to feel continuous across a work session.

## Current status

QMeet now supports the core assistant loop:

```text
speak or type -> local/fuzzy command routing -> tool action or streaming chat -> memory/context update
```

Recent progress:

```text
Phase 10  Persistent backend memory
Phase 11  Regression hardening and bug fixes
Phase 12  Active Context / Focus Sessions
```

Phase 12 currently includes:

```text
- backend-persisted activeSession state
- frontend memory-hook support for focus sessions
- focus start/update/read/end commands
- top-bar focus visibility
- focus-aware chat context
- turn focus into tasks
- summarize/save/end focus sessions
```

## What works

```text
- Text input
- Browser voice input
- Spoken responses through browser speech synthesis
- OpenAI-backed streaming chat
- Local command parser before normal chat
- Backend fuzzy command interpretation for natural language commands
- Active Focus Sessions / context engine foundation
- Focus-aware chat context
- Focus-to-task generation
- Focus summary notes
- Web search result cards
- Local notes with backend-backed persistence
- Backend-backed memory/tasks/notes/recent actions/focus context
- Memory import/export/reset controls
- Google Calendar read/create/edit/delete with confirmations
- 1024x600 tablet/kiosk layout polish
- Raspberry Pi Chromium kiosk launcher in scripts/pi-kiosk-start.sh
```

## Requirements

```text
Node.js 20+ recommended
Python 3.11+ recommended
OpenAI API key
Google Calendar OAuth credentials, optional but needed for real calendar actions
```

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

Build and basic backend checks:

```powershell
npm run build
Invoke-RestMethod http://localhost:8000/api/status
Invoke-RestMethod http://localhost:8000/api/calendar/status
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=today"
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
start a coding focus session for QMeet Phase 12
set my goal to polish the focus summary flow
what is my focus
what should I do next
turn this focus into tasks
make tasks for my current goal
summarize this focus
save this focus as a note
end and summarize this focus
end focus session
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

## Memory and storage

Backend memory is primary. The backend stores memory in:

```text
backend/data/qmeet_memory.json
```

Current backend memory categories:

```text
tasks
notes
recentActions
activeSession
```

The frontend keeps browser fallback copies so the tablet UI remains resilient during backend outages or first-run migration.

Important frontend storage keys:

```text
qmeet-notes
qmeet-calendar-events
qmeet-memory-tasks
qmeet-recent-actions
qmeet-active-session
qmeet-active-session-live
qmeet-voice-output-enabled
qmeet-speech-rate
```

Google Calendar OAuth tokens are backend-local files, not browser storage.

## Do not commit secrets

Keep these files local only:

```text
.env.local
backend/.env
backend/google_credentials.json
backend/token_calendar_readonly.json
backend/token_calendar_events.json
backend/calendar_auth_state.json
```

## More docs

```text
docs/development.md              setup details, API endpoints, phase notes, troubleshooting
docs/architecture.md             current frontend/backend architecture snapshot
docs/phase-12-context-engine.md  Active Context / Focus Sessions design and progress
docs/pi-kiosk.md                 Raspberry Pi kiosk launch/autostart notes
```

## Project structure

```text
QMeet1/
├─ src/app/
│  ├─ App.tsx
│  ├─ api.ts
│  ├─ commands.ts
│  ├─ types.ts
│  ├─ components/
│  │  └─ TopStatusBar.tsx
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
└─ scripts/
```
