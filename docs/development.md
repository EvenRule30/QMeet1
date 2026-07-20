# QMeet Development Notes

This file keeps detailed project/setup information out of the main README.

## Current project state

QMeet is currently through Phase 16C.

```text
Phase 10 completed: backend-backed persistent memory
Phase 11 completed: regression audit and bug hardening
Phase 12 completed: active context / focus sessions
Phase 13 completed: workflow memory, nudges, focus history, and recaps
Phase 14 completed: visual context, camera snapshot analysis, image analysis, and visual commands
Phase 15 completed: visual-focus fusion, upload analysis polish, discreet chat-log toggle, docs
Phase 16 completed through 16C: calendar-aware focus prep, meeting prep tasks, notes, follow-up tasks, and wrap-up
```

The most important current architecture rule is that backend memory is primary after initialization. Browser `localStorage` is still used as a fallback and migration source, but it should not overwrite intentionally empty backend memory, backend focus history archives, backend visual context, or calendar-generated task/focus state.

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
│  ├─ notes, memory, calendar, search, settings, status, camera panels/overlays
│  ├─ active focus/session state and recent focus history
│  ├─ workflow nudges, focus actions, local/enhanced recaps
│  ├─ visualContext state and manual/camera/uploaded-image observations
│  ├─ meeting-prep focus and meeting wrap-up workflows
│  ├─ discreet chat-log toggle
│  └─ chat streaming controller with focus-aware and visual-context-aware prompts
└─ FastAPI backend
   ├─ OpenAI chat streaming
   ├─ OpenAI vision snapshot analysis
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

`backend/.env` controls model, CORS, snapshot limits, and Google Calendar behavior.

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
visualContext
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
qmeet-visual-context
```

Important behavior:

```text
- If backend memory has never been initialized, browser fallback memory can migrate into it.
- If backend memory exists but is empty, that empty state is treated as intentional.
- Memory import/export/reset should operate through backend memory first.
- Browser fallback should recover UI state when backend is unavailable, not become the source of truth forever.
- Ending an active focus archives it into recentFocusSessions before clearing activeSession.
- Full memory context saves should preserve recentFocusSessions and visualContext when the client does not explicitly replace them.
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
start a coding focus session for QMeet Phase 16
coding focus
set my goal to test calendar focus
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

## Visual context and camera commands

Manual visual observation commands:

```text
note visually that the prototype tablet is on the desk
remember visually that I am looking at the whiteboard
visual note that the charger is plugged in
```

Visual read/history/summary commands:

```text
what was the last thing you saw
what did you last see
what am I looking at
show visual observations
visual history
camera history
summarize visual context
visual recap
show visual context
delete last visual observation
clear visual context
```

Visual-focus commands:

```text
save this visual context to my focus
link latest visual observation to my focus
pin what you saw to the current focus
show visuals for my focus
show visual observations linked to my focus
```

Camera overlay commands through the prompt bar:

```text
open camera
camera preview
take snapshot
capture snapshot
close camera
```

Camera behavior:

```text
- Browser preview uses getUserMedia.
- Snapshot stays in browser memory until cleared/closed/analyzed.
- Analyze Snapshot sends the current image through the backend to OpenAI vision.
- Uploaded images can also be analyzed through the same backend vision route.
- QMeet stores only the returned text summary as a VisualObservation.
- Raw images are not stored in localStorage, sessionStorage, backend/data, or qmeet_memory.json.
- Normal chat receives the last saved visual observation as text context, not live camera access.
- If webcam preview becomes stale/blurred, Reset preview performs the current UI-level workaround.
```

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

## Calendar-focus workflow commands

Phase 16 adds a meeting lifecycle on top of Google Calendar, active focus, notes, and tasks.

Meeting prep:

```text
prepare me for my next meeting
start a focus session for my next calendar event
what should I work on before my next event
summarize my schedule and focus priorities
calendar focus
```

Meeting prep tasks:

```text
make prep tasks for my next meeting
turn my next meeting into tasks
next meeting prep tasks
```

Meeting wrap-up:

```text
summarize this meeting
save meeting notes
create follow-up tasks from this meeting
meeting follow-up tasks
wrap up this meeting
end meeting with summary
```

Behavior:

```text
- Calendar-focus prep opens/refreshes Calendar, selects the next upcoming event, and starts a meeting-prep focus.
- Prep tasks are generated from the event title, time, location, and description when available.
- Prep task IDs are linked to the active focus.
- Save meeting notes creates a note from the active meeting focus summary.
- Follow-up task commands create linked meeting follow-up tasks.
- Wrap up this meeting creates follow-up tasks, saves a summary note, and ends the active focus.
```

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

Search test:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/search" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"query":"raspberry pi chromium kiosk mode"}'
```

## Regression test script

After major memory/focus/visual/calendar changes, run this manually from the QMeet prompt:

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
note visually that the prototype tablet is on the desk
what was the last thing you saw
show visual observations
summarize visual context
open camera
take snapshot
Analyze Snapshot
what am I looking at
save this visual context to my focus
show visuals for my focus
end focus anyway
show recent focus sessions
```

Calendar workflow regression:

```text
prepare me for my next meeting
what is my focus
open memory
make prep tasks for my next meeting
save meeting notes
create follow-up tasks from this meeting
wrap up this meeting
open notes
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
- manual visual note appears in Memory panel Visual Context
- camera snapshot can be analyzed into a camera observation
- chat can answer from the last saved visual observation without claiming live camera access
- calendar-focus prep chooses the next event and starts a meeting-prep focus
- meeting prep tasks appear immediately in Memory
- save meeting notes creates a note
- wrap up this meeting creates follow-up tasks, saves a note, and ends/archives the focus
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

### Memory/tasks/focus/visual context disappeared

Check whether the backend memory file exists:

```text
backend/data/qmeet_memory.json
```

Check backend memory status:

```powershell
Invoke-RestMethod http://localhost:8000/api/memory/status
Invoke-RestMethod http://localhost:8000/api/memory/context
Invoke-RestMethod http://localhost:8000/api/memory/sessions/recent
Invoke-RestMethod http://localhost:8000/api/memory/visual
```

Browser fallback can also be inspected in DevTools:

```text
Application -> Local storage -> qmeet-memory-tasks
Application -> Local storage -> qmeet-notes
Application -> Local storage -> qmeet-recent-actions
Application -> Local storage -> qmeet-active-session
Application -> Local storage -> qmeet-recent-focus-sessions
Application -> Local storage -> qmeet-visual-context
```

### Calendar-focus prep does not work

Check:

```text
- Google Calendar is connected in the Calendar panel
- backend calendar status is healthy
- calendar events are visible from /api/calendar/events
- frontend/backend were both restarted after route/parser changes
```

If Google Calendar is disconnected, QMeet should fall back to local calendar events when available.

### Save meeting notes creates no note

Check:

```text
- useMemoryContext includes the summary-note event listener
- Notes panel opens after saving meeting notes
- qmeet_memory.json notes array changes after the command
```

The fixed path creates the note before ending/clearing the active meeting focus.

### Camera preview does not work

Check:

```text
- browser supports getUserMedia
- page is running on localhost or HTTPS
- camera permission is allowed
- no other app is locking the camera
- camera overlay was opened from the prompt or floating camera control
```

### Snapshot analysis fails

Check:

```text
- backend is running
- backend/app/routers/visual.py is included from backend/app/main.py
- OPENAI_API_KEY is set if using real vision
- OPENAI_VISION_MODEL is set or defaulted
- image is jpeg/png/webp
- image size is below QMEET_MAX_SNAPSHOT_BYTES
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

Do not commit snapshot images, uploaded test images, or personal media unless they are intentional fixture assets.

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
Phase 14A Backend visualContext persistence
Phase 14B Frontend visualContext integration
Phase 14C Manual visual observation commands
Phase 14D Camera readiness architecture doc
Phase 14E One-shot camera preview and snapshot UI
Phase 14F Snapshot analysis and camera observations
Phase 14G Visual context in chat
Phase 14H Visual context command polish
Phase 14I Docs update for camera and visual context
Phase 15A Visual-focus fusion
Phase 15B Uploaded image analysis support
Phase 15C Discreet chat-log toggle
Phase 15D Phase 15 docs update
Phase 16A Calendar-aware focus prep
Phase 16B Meeting prep task generation
Phase 16C Meeting notes, follow-up tasks, and wrap-up
Phase 16D Phase 16 docs and regression checklist
```

## Next direction

Phase 16 established the calendar-to-focus lifecycle:

```text
calendar event -> prep focus -> prep tasks -> meeting notes -> follow-up tasks -> wrap-up/archive
```

The next major direction can be:

```text
Phase 17A Day-planning dashboard from calendar + focus + tasks
Phase 17B Proactive reminders/nudges around upcoming calendar events
Phase 17C Meeting-specific note templates or richer agenda extraction
```
