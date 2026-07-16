# QMeet Development Notes

This file keeps detailed project/setup information out of the main README.

## Architecture

```text
QMeet
├─ React / Vite / TypeScript frontend
│  ├─ interactive orb UI
│  ├─ browser speech recognition
│  ├─ browser speech synthesis
│  ├─ local command parser
│  ├─ local notes and memory panels
│  ├─ Active Focus Session UI/state
│  ├─ Google Calendar panel
│  └─ web search panel
└─ FastAPI backend
   ├─ OpenAI chat streaming
   ├─ OpenAI web search wrapper
   ├─ command interpretation endpoint
   ├─ deterministic focus command routing helpers
   ├─ Google Calendar OAuth/API integration
   └─ backend JSON memory store
```

## Main local URLs

```text
Frontend: http://localhost:5173
Backend:  http://localhost:8000
```

For testing from a Raspberry Pi on the same network, set the frontend API URL to the laptop IP:

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

## Backend memory

Backend memory is the source of truth when available. It is stored as local JSON:

```text
backend/data/qmeet_memory.json
```

Current memory categories:

```text
tasks
notes
recentActions
activeSession
```

Phase 10 made backend memory primary. The frontend still keeps local browser fallback copies and migrates old local memory into the backend only when the backend memory file has not been initialized yet.

The memory file is written with an atomic temp-file/replace flow and guarded by an in-process lock to reduce local JSON corruption and overlapping write issues.

## Frontend local fallback storage

Frontend localStorage/sessionStorage keys include:

```text
qmeet-notes                         notes fallback
qmeet-calendar-events               local fallback calendar events
qmeet-memory-tasks                  task fallback
qmeet-recent-actions                compact recent action log used by memory readout
qmeet-active-session                active focus/session fallback
qmeet-active-session-live           same-tab focus/session live mirror
qmeet-voice-output-enabled          voice output setting
qmeet-speech-rate                   speech speed setting
```

Backend memory should be treated as primary for tasks, notes, recent actions, and focus sessions. Browser storage is mainly fallback/migration state.

## Local memory / tasks / focus

Memory panel supports tasks, notes, recent action summaries, and Active Focus Sessions.

Task commands:

```text
open memory
what was I working on
remember to test the Pi kiosk as a task
mark task done
mark task test the Pi done
clear completed tasks
close memory
```

Focus commands:

```text
start a focus session for QMeet Phase 12
start a coding focus session for QMeet Phase 12
set current focus on camera architecture
set my goal to improve focus-aware chat
what is my focus
what should I do next
turn this focus into tasks
make tasks for my current goal
summarize this focus
save this focus as a note
save this session to memory
end and summarize this focus
end focus session
```

Focus behavior:

```text
- activeSession is persisted in backend memory.
- the top status bar displays the current focus.
- normal chat receives neutral active-focus context.
- focus-to-tasks creates deterministic memory tasks and links them to the session.
- focus summaries can be saved as notes and optionally end the session.
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

## Useful API checks

```powershell
Invoke-RestMethod http://localhost:8000/api/status
Invoke-RestMethod http://localhost:8000/api/calendar/status
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=today"
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=tomorrow"
Invoke-RestMethod http://localhost:8000/api/memory/status
Invoke-RestMethod http://localhost:8000/api/memory/context
Invoke-RestMethod http://localhost:8000/api/memory/session
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

Active session API examples:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/memory/session" `
  -Method PUT `
  -ContentType "application/json" `
  -Body '{"title":"QMeet Phase 12","mode":"coding","goal":"finish focus docs"}'

Invoke-RestMethod http://localhost:8000/api/memory/session

Invoke-RestMethod `
  -Uri "http://localhost:8000/api/memory/session" `
  -Method DELETE
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
start a coding focus session for QMeet Phase 12
set my goal to polish the focus workflow
what is my focus
turn this focus into tasks
summarize this focus
save this focus as a note
end and summarize this focus
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

### Voice input does not work

Browser speech recognition depends on browser support and microphone permissions. Chrome/Chromium is the expected browser path.

### Memory/tasks/focus disappeared

Check backend memory first:

```powershell
Invoke-RestMethod http://localhost:8000/api/memory/status
Invoke-RestMethod http://localhost:8000/api/memory/context
```

Then check browser fallback storage:

```text
Application -> Local storage -> qmeet-memory-tasks
Application -> Local storage -> qmeet-active-session
Application -> Session storage -> qmeet-active-session-live
```

### Focus commands go to chat instead of a tool update

Check that both frontend and backend were restarted/reloaded after replacing files:

```text
npm run build
restart Vite dev server if needed
restart uvicorn backend
```

Focus command routing is split across:

```text
src/app/commands.ts
src/app/commandHandlers/memory.ts
backend/app/routers/command.py
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
Phase 9G  Refactor arc / architecture cleanup
Phase 10  Backend persistent memory
Phase 11  Regression hardening and bug discovery
Phase 12A Backend activeSession persistence
Phase 12B Frontend activeSession memory hook support
Phase 12C Focus session commands
Phase 12D Visible focus + backend focus routing + focus-aware chat context
Phase 12E Focus-to-tasks and focus summary/save/end flows
Phase 12F Documentation refresh
```
