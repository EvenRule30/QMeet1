# QMeet

QMeet is a voice-first AI tablet interface for the Chascii orb prototype. The frontend is a React/Vite app built around an interactive orb UI, and the backend is a FastAPI service for chat, command interpretation, web search, Google Calendar actions, persistent memory, workflow context, visual observations, and camera snapshot analysis.

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
- Browser camera preview and one-shot snapshot capture
- Snapshot analysis through the backend vision route
- Uploaded image analysis through the same visual route
- Visual context in normal chat
- Explicit visual context read/history/summary commands
- Visual observations linked to active focus sessions
- Discreet chat-log toggle without starting voice input
- Calendar-aware meeting-prep focus sessions
- Calendar-derived meeting prep tasks
- Meeting notes, follow-up tasks, and meeting wrap-up commands
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
Phase 14  Visual context and one-shot camera observation pipeline
Phase 15  Visual-focus fusion, image upload analysis, discreet chat-log toggle
Phase 16  Calendar-focus lifecycle: meeting prep, prep tasks, notes, follow-up, wrap-up
```

## Requirements

- Node.js 20+ recommended
- Python 3.11+ recommended
- OpenAI API key
- Google Calendar OAuth credentials, optional but needed for real calendar actions
- Browser with `navigator.mediaDevices.getUserMedia` for camera preview/capture, preferably Google Chrome

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
OPENAI_VISION_MODEL=gpt-4.1-mini
OPENAI_MAX_OUTPUT_TOKENS=300
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

Snapshot analysis test from PowerShell:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/visual/analyze-snapshot" `
  -ContentType "image/png" `
  -InFile ".\snapshot.png"
```

## Common prompt examples

```text
start a coding focus session for QMeet Phase 16
what is my focus
turn this focus into tasks
save this focus as a note
what was my last focus
resume my last focus
summarize what I worked on today
give me a better recap of today
```

Calendar-focus lifecycle:

```text
prepare me for my next meeting
what is my focus
turn this focus into tasks
save meeting notes
create follow-up tasks from this meeting
wrap up this meeting
open notes
show recent focus sessions
```

Visual/camera examples:

```text
open camera
take snapshot
Analyze Snapshot
what was the last thing you saw
save this visual context to my focus
show visuals for my focus
```

## Raspberry Pi kiosk mode

The Pi kiosk setup is separate and documented in:

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

Do not commit snapshot images, uploaded camera test images, or other personal media unless they are intentional fixture assets.

## More docs

- `docs/development.md` - setup details, API endpoints, phase history, testing, troubleshooting
- `docs/architecture.md` - current frontend/backend architecture snapshot
- `docs/pi-kiosk.md` - Raspberry Pi kiosk launch/autostart notes

## Main project structure

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
│  │  └─ ChatLogToggle.tsx
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
