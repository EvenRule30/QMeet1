# QMeet Development Notes

This file keeps detailed project/setup information out of the main README.

## Current project state

QMeet is currently through Phase 13F and ready for either Phase 13G polish/regression work or the first Phase 14 camera-readiness architecture slice.

```text
Phase 10 completed: backend-backed persistent memory
Phase 11 completed: regression audit and bug hardening
Phase 12 completed: active context / focus sessions
Phase 13 completed through 13F: workflow memory, nudges, focus history, and recaps
```

The most important current architecture rule is that backend memory is primary after initialization. Browser `localStorage` is still used as a fallback and migration source, but it should not overwrite an intentionally empty backend memory file or a backend focus history archive.

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
│  ├─ active focus/session state and recent focus history
│  └─ chat streaming controller with focus-aware context
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
activeSession
recentFocusSessions
```

The backend memory store is file-based and prototype-local. Phase 11 hardened it with atomic writes and an in-process lock so overlapping memory saves are less likely to corrupt or lose data.

The frontend memory hook keeps browser fallback copies under:

```text
qmeet-notes
qmeet-memory-tasks
qmeet-recent-actions
qmeet-active-session
qmeet-active-session-live
qmeet-recent-focus-sessions
```

Important behavior:

```text
- If backend memory has never been initialized, browser fallback memory can migrate into it.
- If backend memory exists but is empty, that empty state is treated as intentional.
- Memory import/export/reset should operate through backend memory first.
- Browser fallback should recover UI state when backend is unavailable, not become the source of truth forever.
- Ending an active focus archives it into recentFocusSessions before clearing activeSession.
- Full memory context saves should preserve recentFocusSessions when the client does not explicitly replace them.
```

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
Recent Actions stored internally for summary context
Destructive task actions are confirmation-gated through the existing command safety flow
```

## Active focus / context commands

Main commands:

```text
start a coding focus session for QMeet Phase 13
coding focus
set my goal to test workflow memory
what is my current focus
end focus
end focus anyway
end with summary
save this focus as a note
turn this focus into tasks
what was my last focus
show recent focus sessions
resume my last focus
restart the last coding focus
```

Behavior:

```text
Active focus is visible in the top status bar and Memory panel.
Focus actions are available in the Memory panel.
Focus nudges suggest setting a goal, creating tasks, saving a note, or ending with summary.
Ending a focus with meaningful progress and no saved summary asks the user to save first or end anyway.
Ended focus sessions are archived into recentFocusSessions.
```

## Recap commands

Local deterministic recap:

```text
summarize what I worked on today
today focus recap
recap my focus sessions
what did I focus on recently
what changed since yesterday
weekly focus recap
```

Enhanced LLM recap:

```text
give me a better recap of today
ai focus recap yesterday
summarize my recent progress
what should I focus on next
weekly work recap with recommendations
```

Local recap is deterministic and uses memory data directly. Enhanced recap sends a compact memory snapshot through the normal chat stream and asks the model for a concise recap, what changed, open loops, and a suggested next action.

## Google Calendar setup

Expected local files inside `backend/`:

```text
google_credentials.json
token_calendar_events.json
calendar_auth_state.json
```

`google_credentials.json` comes from Google Cloud OAuth credentials. The token/state files are generated locally after authorization.

Calendar writing is guarded by frontend confirmations for destructive or real-calendar actions.

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
Invoke-RestMethod http://localhost:8000/api/memory/session
Invoke-RestMethod http://localhost:8000/api/memory/sessions/recent
```

Search test:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/search" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"query":"raspberry pi chromium kiosk mode"}'
```

Memory context test:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/memory/tasks" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"title":"Test persistent memory"}'
```

## Regression test script

After major memory/focus changes, run this manually from the QMeet prompt:

```text
open memory
start a coding focus session for regression testing
set my goal to verify focus lifecycle
what is my current focus
turn this focus into tasks
save this focus as a note
end focus
cancel
end with summary
what was my last focus
resume my last focus
what should I focus on next
summarize what I worked on today
give me a better recap of today
end focus anyway
show recent focus sessions
```

Expected results:

```text
- focus appears in top status bar and Memory panel
- linked tasks are created
- saved summary opens Notes
- plain end focus guard asks to save or end anyway when needed
- end with summary archives the session
- last focus recall reads the archived session
- resume creates a new active session from history
- local recap returns deterministic memory summary
- enhanced recap streams a ChatGPT response using memory context
```

## Layout notes

The UI target is Raspberry Pi 1024x600 landscape. Normal laptop development should still use the browser/devtools workflow:

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

### Memory/tasks/focus disappeared

Check whether the backend memory file exists:

```text
backend/data/qmeet_memory.json
```

Check backend memory status:

```powershell
Invoke-RestMethod http://localhost:8000/api/memory/status
Invoke-RestMethod http://localhost:8000/api/memory/context
Invoke-RestMethod http://localhost:8000/api/memory/sessions/recent
```

Browser fallback can also be inspected in DevTools:

```text
Application -> Local storage -> qmeet-memory-tasks
Application -> Local storage -> qmeet-notes
Application -> Local storage -> qmeet-recent-actions
Application -> Local storage -> qmeet-active-session
Application -> Local storage -> qmeet-recent-focus-sessions
```

### Recent focus sessions do not appear

Check:

```text
- backend was restarted after applying focus-history backend files
- backend/data/qmeet_memory.json has recentFocusSessions
- frontend useMemoryContext includes recentFocusSessions
- browser localStorage key qmeet-recent-focus-sessions is not stale or malformed
```

Ending a focus should archive it before clearing `activeSession`.

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
Phase 12A Backend activeSession persistence
Phase 12B Frontend activeSession memory integration
Phase 12C Focus commands
Phase 12D Visible focus, backend routing, focus-aware chat context
Phase 12E Focus actions: tasks, summaries, notes
Phase 12F Phase 12 docs update
Phase 13A Focus nudges
Phase 13B Clickable and always-available focus actions
Phase 13C End-of-focus guard
Phase 13D Recent focus history
Phase 13E Focus history recall/resume commands
Phase 13F Local and LLM-enhanced recaps
Phase 13G Docs and regression checklist
```

## Phase 11 regression hardening log

```text
- Backend memory writes are locked and atomic.
- Task completion PATCH handling preserves completedAt when the field is omitted.
- Duplicate close-memory toast switch case removed.
- Chat stream SSE parsing is more robust and reports premature stream closure.
- Chat failure message uses configured VITE_QMEET_API_URL instead of hardcoded localhost.
- Spoken prompt submission immediately sets the orb into a thinking/routing state.
- Google Calendar confirmed delete/edit refreshes connected calendar state before resolving cold-start targets.
```

## Phase 12 and 13 direction

Phase 12 added active context/focus sessions. Phase 13 made that context actionable and persistent across sessions.

The next major direction is Phase 14 camera-readiness architecture: define a future visual observation model that plugs into active context without committing too early to a specific camera hardware path.
