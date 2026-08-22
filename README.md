# QMeet

QMeet is a voice-first AI tablet interface built around the Chascii orb concept. The prototype combines a React/Vite tablet UI with a FastAPI backend and is designed so a user can talk to QMeet naturally instead of navigating traditional app menus for every task.

The main hardware target is a 1024x600 Raspberry Pi/tablet-style display, but normal development runs in a desktop browser.

This README is intentionally a run guide. For the current agent, Focus, state-ownership, and execution architecture, see `docs/architecture.md`. For regression workflow and development conventions, see `docs/development.md`.

## Requirements

- Node.js 20+ recommended
- Python 3.11+ recommended
- Chrome or another browser with microphone/camera support for voice and camera features
- An OpenAI API key for real AI behavior; mock mode can be used without one
- Google Calendar OAuth credentials only if you want connected Calendar actions

## Run QMeet locally

QMeet uses two local processes:

- FastAPI backend on port `8000`
- Vite frontend on port `5173`

### 1. Start the backend

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

The checked-in `backend/.env.example` defaults to mock mode, so you can verify the application shell before configuring an API key.

Start FastAPI from `backend/`:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Check that the backend is reachable:

```text
http://localhost:8000/health
```

Expected response:

```json
{"ok":true,"service":"qmeet-agent"}
```

### 2. Start the frontend

Open a second terminal at the repository root:

```bash
npm install
```

Create `.env.local`:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

Start Vite:

```bash
npm run dev -- --host 0.0.0.0
```

Open the displayed Vite URL, normally:

```text
http://localhost:5173
```

If the UI loads but QMeet reports that the backend is unavailable, verify the backend health URL first and then confirm `VITE_QMEET_API_URL`.

## Enable real OpenAI responses

Edit `backend/.env` and set at minimum:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4.1-mini
FRONTEND_ORIGIN=http://localhost:5173
```

Restart FastAPI after changing backend environment variables.

The current `.env.example` also contains guarded Focus-routing settings. Leave those defaults in place unless you are intentionally testing the routing/Focus architecture described in `docs/development.md`.

## Google Calendar setup

Calendar integration is optional. QMeet can run without Google credentials.

To enable it, create a Google OAuth client that can access Calendar, put the downloaded credentials file in `backend/`, and configure `backend/.env`:

```env
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CALENDAR_WRITE_ENABLED=true
GOOGLE_CALENDAR_CREDENTIALS_FILE=google_credentials.json
GOOGLE_CALENDAR_TOKEN_FILE=token_calendar_events.json
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8000/api/calendar/auth/callback
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=local
```

Restart the backend after changing these values. QMeet will create its local Calendar token/auth-state files during authorization.

Useful checks:

```powershell
Invoke-RestMethod http://localhost:8000/api/calendar/status
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=today"
```

Calendar writes are deliberately separate from language interpretation. QMeet can interpret a natural request, but the existing deterministic Calendar path still resolves the requested target and applies confirmation/validation before a write is treated as complete.

## First-run smoke test

After the frontend and backend are running, a short manual pass is usually enough to catch setup problems:

```text
hello
show my tasks
what is my focus
what is on my calendar today
open settings
```

If OpenAI mode is enabled, also try a normal conversational question and a natural tool request such as:

```text
search for Framework Laptop reviews
create a project meeting tomorrow at 3 PM
```

If Calendar is not configured, skip the Calendar write test.

### Focus sanity check

Active Focus is canonical backend state, not just a frontend Memory projection. A useful read-only check is:

```text
what is my focus
```

When a Focus has a next step, the readout should include it. The canonical state is also available through:

```text
GET /api/focus/state
```

Do not edit `backend/data/qmeet_focus.json` manually while the backend is running.

## Using QMeet

QMeet is in a staged unified-agent transition. You do not need to memorize rigid command syntax for the promoted paths: natural requests can be classified by the agent and then handed to deterministic feature code for validation and execution.

A few representative requests:

```text
show my tasks
remember to compare laptops
I finished the presentation outline
show my notes
search for Framework Laptop reviews
what is on my calendar Friday
create a project meeting tomorrow at 3 PM
start a focus to plan a vacation
what should I do today?
what is my focus
open calendar
mute voice
```

An active Focus provides context when relevant, but it does not own every conversation. Unrelated Calendar, Search, task, device, or general-chat requests should remain independent unless the user actually connects them to the Focus.

## Local data and secrets

Keep these files local and out of commits:

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

The two main prototype-local state files have different ownership:

- `backend/data/qmeet_memory.json` stores general Memory data such as tasks, notes, recent actions, and visual observations.
- `backend/data/qmeet_focus.json` is the canonical Focus event/state store. Legacy Memory projections may still exist for compatibility, but they are not authoritative for runtime Focus ownership.

## Tests

Run the full backend regression suite from `backend/` with the virtual environment active:

```bash
python -m unittest discover -s tests -v
```

Build the frontend from the repository root:

```bash
npm run build
```

For changes to agent routing, Focus, Calendar, tasks, or continuation behavior, run the relevant targeted regression files first and then the full backend suite. See `docs/development.md` for the current test strategy.

## Raspberry Pi / kiosk mode

The Pi launcher is separate from normal laptop development:

```text
docs/pi-kiosk.md
scripts/pi-kiosk-start.sh
```

When the Pi opens a frontend hosted by another machine, point the frontend at that machine's LAN address rather than `localhost`:

```env
VITE_QMEET_API_URL=http://YOUR_LAPTOP_IP:8000
```

Then launch the Pi kiosk with:

```bash
chmod +x scripts/pi-kiosk-start.sh
QMEET_URL=http://YOUR_LAPTOP_IP:5173 ./scripts/pi-kiosk-start.sh
```

See `docs/pi-kiosk.md` for Chromium permissions, scaling, autostart, and troubleshooting.

## Troubleshooting

### Frontend says the backend is offline

1. Open `http://localhost:8000/health`.
2. Confirm FastAPI was started from `backend/`.
3. Confirm `.env.local` uses the backend address that the browser can actually reach.
4. Restart Vite after changing `.env.local`.

### OpenAI responses are still mocked

Check `backend/.env`:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=...
```

Then restart FastAPI. The checked-in example intentionally uses `LLM_PROVIDER=mock`.

### Calendar is disconnected

Check:

```text
http://localhost:8000/api/calendar/status
```

Then verify the OAuth credential filename, redirect URI, and `GOOGLE_CALENDAR_ENABLED` / `GOOGLE_CALENDAR_WRITE_ENABLED` values.

### Voice or camera does not work

Browser microphone and camera permissions are stored by the browser profile. On a Pi kiosk, the launcher uses a persistent Chromium profile so those permissions can survive relaunches. See `docs/pi-kiosk.md`.

### Focus readout looks stale

Use `what is my focus` or inspect `GET /api/focus/state`. Canonical Focus state is authoritative; stale legacy Memory/session projections should not be used to decide whether a Focus is active.

## Documentation

- `docs/README.md` - documentation map and which files are current vs historical
- `docs/architecture.md` - current runtime architecture, state ownership, unified-agent promotion, Focus, and deterministic execution boundaries
- `docs/development.md` - developer workflow, tests, architecture guardrails, and current transition seams
- `docs/pi-kiosk.md` - Raspberry Pi kiosk setup
- `docs/phase-14-camera-readiness.md` - historical camera-readiness notes
- `docs/qmeet-guide-spec.md` - reference/design document; not the runtime architecture source of truth

For a new contributor, start here, then read `docs/architecture.md` before changing routing or state ownership.
