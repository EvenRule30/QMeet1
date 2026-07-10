# QMeet

QMeet is a voice-first AI tablet interface for the Chascii orb prototype. The frontend is a React/Vite app built around an interactive orb UI, and the backend is a FastAPI service for chat, web search, and Google Calendar actions.

## What works

- Text and browser voice input
- Spoken responses through browser speech synthesis
- OpenAI-backed chat streaming
- Local command routing before normal chat
- Web search result cards
- Local notes
- Local memory/tasks in browser storage
- Google Calendar read/create/edit/delete with confirmations
- 1024×600 tablet/kiosk layout polish
- Raspberry Pi Chromium kiosk launcher in `scripts/pi-kiosk-start.sh`

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

## Local browser storage

These are browser-local prototype stores. Clearing site data or switching browsers/devices can hide or remove them.

```text
qmeet-notes
qmeet-calendar-events
qmeet-memory-tasks
qmeet-recent-actions
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

- `docs/development.md` — setup details, API endpoints, Google Calendar notes, troubleshooting
- `docs/pi-kiosk.md` — Raspberry Pi kiosk launch/autostart notes
