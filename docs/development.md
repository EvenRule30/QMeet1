# QMeet Development Notes

This file keeps detailed project/setup information out of the main README.

## Current project state

QMeet is currently past Phase 11 and ready to begin Phase 12.

```text
Phase 10 completed: backend-backed persistent memory
Phase 11 completed/in progress: regression audit and bug hardening
Phase 12 next: active context / focus sessions
```

The most important current architecture rule is that backend memory is primary after initialization. Browser `localStorage` is still used as a fallback and migration source, but it should not overwrite an intentionally empty backend memory file.

## Architecture

```text
QMeet
├─ React / Vite / TypeScript frontend
│  ├─ interactive orb UI
│  ├─ browser speech recognition
│  ├─ browser speech synthesis
│  ├─ local exact command parser
│  ├─ backend fuzzy command interpreter client
│  ├─ command/result toast cards
│  ├─ notes, memory, calendar, search, settings, status panels
│  └─ chat streaming controller
└─ FastAPI backend
   ├─ OpenAI chat streaming
   ├─ OpenAI web search wrapper
   ├─ command interpretation endpoint
   ├─ Google Calendar OAuth/API integration
   └─ backend-local JSON memory store
```

## Main local URLs

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8000
```

For testing from a Raspberry Pi or another device on the same network, set the frontend API URL to the laptop IP:

```env
VITE_QMEET_API_URL=http://YOUR_LAPTOP_IP:8000
```

Then restart Vite.

## Backend commands

Windows PowerShell:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Linux/macOS:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Frontend commands

```powershell
npm install
npm run dev -- --host 0.0.0.0
npm run build
```

## Backend environment

`backend/.env` controls model, CORS, and Google Calendar behavior.

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

## Frontend environment

Local laptop testing:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

Pi testing against laptop-hosted backend:

```env
VITE_QMEET_API_URL=http://YOUR_LAPTOP_IP:8000
```

Restart Vite after changing `.env.local`.

## Persistent memory

Primary memory lives in:

```text
backend/data/qmeet_memory.json
```

Current stored categories:

```text
tasks
notes
recentActions
```

The backend memory store is file-based and prototype-local. Phase 11 hardened it with atomic writes and an in-process lock so overlapping memory saves are less likely to corrupt or lose data.

The frontend memory hook keeps browser fallback copies under:

```text
qmeet-notes
qmeet-memory-tasks
qmeet-recent-actions
```

Important behavior:

```text
- If backend memory has never been initialized, browser fallback memory can migrate into it.
- If backend memory exists but is empty, that empty state is treated as intentional.
- Memory import/export/reset should operate through backend memory first.
- Browser fallback should recover UI state when backend is unavailable, not become the source of truth forever.
```

## Local browser storage

QMeet currently uses these browser keys for fallback state and UI preferences:

```text
qmeet-notes                  fallback note copy
qmeet-calendar-events        local fallback calendar events
qmeet-memory-tasks           fallback task/memory list
qmeet-recent-actions         compact recent action log used by memory readout
qmeet-voice-output-enabled   voice output setting
qmeet-speech-rate            speech speed setting
```

Voice settings and local fallback state are browser-local. Backend memory and Google Calendar tokens are backend-local.

## Local memory / tasks

Main commands:

```text
open memory
what was I working on
remember to test the Pi kiosk as a task
mark task done
mark task test the Pi done
clear completed tasks
close memory
```

Behavior:

```text
Open Tasks visible in Memory panel
Completed Tasks visible in Memory panel until cleared
Recent Actions stored internally for summary context, hidden from panel UI
Destructive task actions are confirmation-gated through the existing command safety flow
```

## Google Calendar setup

Expected local files inside `backend/`:

```text
google_credentials.json
token_calendar_events.json
calendar_auth_state.json
```

`google_credentials.json` comes from Google Cloud OAuth credentials. The token/state files are generated locally after authorization. Calendar writing is guarded by frontend confirmations for destructive or real-calendar actions.

Examples:

```text
add event tomorrow at 3 called project sync
delete the 12:00 PM event tomorrow
reschedule last event to tomorrow at 4
rename last event to project sync
```

Phase 11 hardened cold-start calendar delete/edit behavior so confirmed operations refresh Google Calendar before resolving the target event when connected.

## Useful API checks

```powershell
Invoke-RestMethod http://localhost:8000/api/status
Invoke-RestMethod http://localhost:8000/api/calendar/status
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=today"
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=tomorrow"
Invoke-RestMethod http://localhost:8000/api/memory/status
Invoke-RestMethod http://localhost:8000/api/memory/context
Invoke-RestMethod http://localhost:8000/api/memory/export
```

Search test:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/search" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"query":"raspberry pi chromium kiosk mode"}'
```

Calendar create test:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/calendar/events" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"title":"QMeet test event","day":"tomorrow","time":"3 PM"}'
```

Memory context test:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/memory/tasks" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"title":"Test persistent memory"}'
```

## Frontend command examples

```text
open menu
open notes
note that buy milk
read my notes
clear notes
open memory
remember to test the Pi as a task
what was I working on
mark task done
clear completed tasks
open calendar
what's on my calendar
what's on my calendar tomorrow
add event tomorrow at 3 called meeting
confirm
delete the 12:00 PM event tomorrow
cancel
open search
search for chromium kiosk flags
clear search
show status
what did you hear
mute voice
unmute voice
speak slower
speak faster
go home
end chat
```

Phase 12 planned command examples:

```text
start focus session on QMeet Phase 12
start coding mode
set my goal to design camera support
what is my current focus
summarize this session
save this session to memory
end focus session
```

## Layout notes

The UI target is Raspberry Pi 1024x600 landscape.

Normal laptop development should still use the browser/devtools workflow:

```text
npm run dev
Chrome DevTools -> responsive mode -> 1024x600
```

The React app should not force fullscreen, block devtools, hide the cursor globally, or assume it is always running on the Pi. Pi behavior belongs in `scripts/pi-kiosk-start.sh` and `docs/pi-kiosk.md`.

## Common troubleshooting

### Frontend cannot reach backend

Check:

```text
backend is running on port 8000
.env.local has the correct VITE_QMEET_API_URL
FRONTEND_ORIGIN matches the frontend URL
Vite was restarted after env changes
```

For Pi/laptop testing, do not use `localhost` from the Pi unless the backend is also running on the Pi. Use the laptop LAN IP.

### Voice input does not work

Browser speech recognition depends on browser support and microphone permissions. Chrome/Chromium is the expected browser path.

### Orb looks ready after speech, before the answer starts

This should be fixed by the Phase 11 voice feedback patch. After final speech transcript submission, the orb should immediately enter a thinking/routing state while command interpretation or chat startup runs.

### Memory/tasks disappeared

Check whether the backend memory file exists:

```text
backend/data/qmeet_memory.json
```

Check backend memory status:

```powershell
Invoke-RestMethod http://localhost:8000/api/memory/status
Invoke-RestMethod http://localhost:8000/api/memory/context
```

Browser fallback can also be inspected in DevTools:

```text
Application -> Local storage -> qmeet-memory-tasks
Application -> Local storage -> qmeet-notes
Application -> Local storage -> qmeet-recent-actions
```

### Google Calendar says not connected

Check:

```text
backend/google_credentials.json exists
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CALENDAR_REDIRECT_URI matches the backend callback
complete auth flow from the Calendar panel
press Refresh after auth
```

### Pi cannot reach laptop backend/frontend

Check:

```text
Pi and laptop are on the same network
use laptop LAN IP, not localhost, from the Pi
backend and frontend are started with --host 0.0.0.0
firewall allows ports 5173 and 8000
```

## Secret files

Do not commit:

```text
.env.local
backend/.env
backend/google_credentials.json
backend/token_calendar_readonly.json
backend/token_calendar_events.json
backend/calendar_auth_state.json
backend/data/qmeet_memory.json
```

## Completed phase summary

```text
Phase 1   Browser speech input
Phase 2   Local UI commands
Phase 3   Browser speech output
Phase 4   Notes / local tools / settings
Phase 5   Fuzzy command interpreter + confirmations
Phase 6   Google Calendar read/create/delete/edit
Phase 7   Web search + result cards
Phase 8A  Voice-first orb activity UI
Phase 8B  Short spoken tool replies
Phase 8C  Command/result toast cards
Phase 8D  1024x600 tablet/kiosk layout polish
Phase 8E  Raspberry Pi kiosk launcher/docs
Phase 8F  Compact README/docs cleanup
Phase 9A  Local memory/task persistence
Phase 9G  Frontend architecture/refactor arc
Phase 10  Backend-backed persistent memory
Phase 11  Regression audit and hardening
```

## Phase 11 regression hardening log

Recent fixes from the Phase 11 audit:

```text
- Backend memory writes are locked and atomic.
- Task completion PATCH handling preserves completedAt when the field is omitted.
- Duplicate close-memory toast switch case removed.
- Chat stream SSE parsing is more robust and reports premature stream closure.
- Chat failure message uses configured VITE_QMEET_API_URL instead of hardcoded localhost.
- Spoken prompt submission immediately sets the orb into a thinking/routing state.
- Google Calendar confirmed delete/edit refreshes connected calendar state before resolving cold-start targets.
```

## Phase 12 direction

Phase 12 should add an active context/focus-session layer. The goal is to let QMeet know what the user is currently working on, not just respond to isolated prompts.

See:

```text
docs/phase-12-context-engine.md
```
