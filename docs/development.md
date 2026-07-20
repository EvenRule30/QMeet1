# QMeet Development Notes

This file keeps detailed project/setup information out of the main README.

## Current project state

QMeet is currently through Phase 15C.

```text
Phase 10 completed: backend-backed persistent memory
Phase 11 completed: regression audit and bug hardening
Phase 12 completed: active context / focus sessions
Phase 13 completed: workflow memory, nudges, focus history, and recaps
Phase 14 completed: visual context, camera snapshot analysis, visual chat context
Phase 15 completed through 15C: visual-focus fusion, uploaded-image analysis fallback, discreet chat-log toggle
```

The most important architecture rule remains that backend memory is primary after initialization. Browser `localStorage` is still used as fallback and migration source, but it should not overwrite initialized backend memory, focus history, or visual context.

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
│  ├─ notes, memory, calendar, search, settings, status, menu panels
│  ├─ active focus/session state and recent focus history
│  ├─ visual context, camera overlay, snapshot/image analysis UI
│  ├─ discreet chat-log toggle
│  └─ chat streaming controller with focus + visual context
└─ FastAPI backend
   ├─ OpenAI chat streaming
   ├─ OpenAI web search wrapper
   ├─ OpenAI vision snapshot analysis endpoint
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

`backend/.env` controls model, CORS, calendar, and vision behavior.

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

## Active focus / context commands

Main commands:

```text
start a coding focus session for QMeet Phase 15
coding focus
set my goal to test visual-focus fusion
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

## Visual context and camera/image analysis

Visual context commands:

```text
note visually that the prototype tablet is on the desk
remember visually that I am looking at the whiteboard
what was the last thing you saw
show visual observations
summarize visual context
show visual context
delete last visual observation
clear visual context
```

Camera and upload flow:

```text
open camera
allow browser camera permission
take snapshot
Analyze Snapshot
open memory
```

Image upload is available inside the camera overlay. It uses the same backend analysis endpoint as webcam snapshots.

Important caveats:

```text
- Webcam preview can blur on some browser/device combinations.
- Reset preview performs the reliable close/reopen lifecycle without manually closing the overlay.
- Camera snapshots and OpenAI analysis can still be sharp even when the preview looks blurry.
- Uploaded images are analyzed from the original uploaded file blob.
- Uploaded images intentionally use a compact no-preview UI because embedded previews showed inconsistent blur artifacts.
- Use Open original when you need to visually inspect the uploaded file.
- QMeet stores only the returned text observation, not the raw uploaded image or snapshot.
```

Visual-focus fusion commands:

```text
save this visual context to my focus
link latest visual observation to my focus
pin what you saw to the current focus
show visuals for my focus
show visual observations linked to my focus
```

Behavior:

```text
- Latest visual observation can be linked to activeSession via relatedFocusId.
- Current Focus card shows linked visual observations.
- Focus summaries include linked visual observations.
- Chat receives compact visual context when available.
```

## Chat-log toggle

Phase 15C added a discreet chat-log button near the lower-left of the UI.

Behavior:

```text
- opens the chat log/prompt area without starting voice input
- does not change orb-click voice behavior
- uses the same smooth layout transition as the normal chat panel
- Escape closes the peek view when idle
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

Visual snapshot endpoint test with PowerShell:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/visual/analyze-snapshot" `
  -ContentType "image/png" `
  -InFile ".\snapshot.png"
```

## Regression test script

After major memory/focus/visual changes, run this manually from the QMeet prompt:

```text
open memory
start a coding focus session for regression testing
set my goal to verify focus and visual lifecycle
what is my current focus
turn this focus into tasks
note visually that the prototype is on the desk
what was the last thing you saw
save this visual context to my focus
show visuals for my focus
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

Camera/upload regression checks:

```text
open camera
verify buttons fit in 1024x600
take snapshot
Analyze Snapshot
open Memory and verify camera observation appears
if webcam preview blurs, use Reset preview
upload an image
Analyze image
open Memory and verify manual/upload observation appears
use Open original to inspect uploaded image if needed
clear visual context
```

Chat-log toggle checks:

```text
click the small chat button in lower-left
verify chat opens without starting voice input
press Escape
verify chat peek closes when idle
click the orb
verify normal voice behavior still works
```

Expected results:

```text
- focus appears in top status bar and Memory panel
- linked tasks are created
- visual observation is saved and can link to focus
- saved summary opens Notes
- plain end focus guard asks to save or end anyway when needed
- end with summary archives the session
- last focus recall reads the archived session
- resume creates a new active session from history
- local recap returns deterministic memory summary
- enhanced recap streams a ChatGPT response using memory and visual context
- camera analysis stores text observations only
- uploaded images are not embedded-preview dependent
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

### Recent focus sessions do not appear

Check:

```text
- backend/data/qmeet_memory.json has recentFocusSessions
- frontend useMemoryContext includes recentFocusSessions
- browser localStorage key qmeet-recent-focus-sessions is not stale or malformed
```

Ending a focus should archive it before clearing `activeSession`.

### Camera preview blurs

Known current workaround:

```text
Use Reset preview from the camera overlay.
```

The preview may blur on some browser/device combinations. The actual captured snapshot and OpenAI analysis may still be sharp. The current workaround reproduces the reliable close/reopen lifecycle without requiring the user to manually close the camera menu.

### Uploaded image preview looks blurry

QMeet intentionally does not rely on embedded uploaded-image previews anymore. Uploaded images are analyzed from the original uploaded file blob. Use **Open original** to inspect the image in the browser's native viewer.

### Visual observation did not save

Check:

```text
- backend is running
- /api/memory/visual returns visualContext
- /api/visual/analyze-snapshot returns ok: true for a test image
- browser localStorage key qmeet-visual-context is not stale or malformed
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
Phase 14E One-shot camera capture UI and close/reset polish
Phase 14F Backend snapshot analysis and camera overlay integration
Phase 14G Visual context in chat
Phase 14H Visual command polish
Phase 14I Camera/visual docs update
Phase 15A Visual-focus fusion
Phase 15B Image upload analysis and compact no-preview upload UI
Phase 15C Discreet chat-log toggle
Phase 15D Docs and regression checklist
```
