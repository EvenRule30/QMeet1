# QMeet1-1

QMeet is a React/Vite prototype for a tablet-style AI home screen. The interface centers on an animated AI orb that can listen, answer, speak aloud, and control local tablet panels, web search, and Google Calendar through voice or typed commands.

The current prototype targets a **1024×600 landscape Raspberry Pi/tablet display** and is currently tested primarily in **Google Chrome / Chromium**.

## Current Capabilities

QMeet currently supports:

- Animated central AI orb UI
- Chat panel with streamed assistant responses
- FastAPI backend connected to OpenAI
- Mock backend mode for testing without OpenAI
- Server-sent events streaming from backend to frontend
- Browser speech-to-text input through the Web Speech API
- Browser speech output through the SpeechSynthesis API
- Local voice/text command routing before sending prompts to OpenAI
- Backend command interpreter agent for fuzzy command detection
- Strict JSON command classification for ambiguous/misheard commands
- Command route/status debugging for exact parser, fuzzy interpreter, and normal chat paths
- Confirmation layer for destructive local commands
- Menu launcher panel
- Settings panel
- Status/system dashboard panel
- Local Notes panel with `localStorage` persistence
- Voice note creation, reading, deleting, and clearing
- Real web search panel powered through the FastAPI backend
- Voice/text search commands with structured result cards
- Search results with summary, recommendation, action steps, useful details, and readable source cards
- Short chat acknowledgement for search commands so full results stay in the Search panel
- Calendar panel with Google Calendar read/create/delete/edit support
- Calendar refresh/sync command and panel refresh button
- Local calendar fallback with `localStorage` event persistence
- Voice calendar event creation, reading, deleting, and clearing
- Google Calendar OAuth through the FastAPI backend
- Google Calendar event creation with confirmation
- Google Calendar event deletion with confirmation for voice/text commands
- Google Calendar event editing, renaming, and rescheduling with confirmation
- Safer delete confirmation that names the exact event before deleting
- Persistent voice output settings across reloads
- Persistent speech speed across reloads
- Voice output settings, including mute/unmute and speech speed control
- Local command help: asking what QMeet can do explains available voice commands
- “What did you hear?” voice debugging
- QMeet name recognition normalization for common speech parser mistakes such as “cue meet,” “queue meet,” or “cute meet”
- Cancel/stop behavior for speech, listening, and active streamed responses
- Listening preview clears when QMeet moves from voice capture into command processing
- Clear Google/local calendar source labels in the Calendar panel
- Conversation reset and backend memory reset
- Laptop-to-Raspberry-Pi LAN testing

## What Runs Locally vs Through OpenAI

QMeet checks exact local commands first. If the frontend parser matches the text, the action runs entirely in the frontend and **does not call normal OpenAI chat**.

If the exact parser does not match, QMeet calls the backend command interpreter. The interpreter returns strict command JSON, not a friendly chat reply. If the result maps to an allowlisted frontend command with enough confidence, the frontend executes that local command. Only when the interpreter says the input is not a command does QMeet send the prompt to normal AI chat.

Examples of local-only actions:

- Opening panels
- Saving notes
- Reading saved notes
- Running web search commands through the backend search endpoint
- Adding calendar events locally or to Google Calendar when connected
- Reading local or Google Calendar events
- Muting/unmuting voice output
- Changing voice speed
- Going home
- Clearing local UI state

Normal prompts that do not match either the exact parser or the fuzzy command interpreter are sent to the FastAPI backend, which then uses the configured AI provider for conversational responses.

The command interpreter never directly changes frontend state. It only classifies intent. The frontend remains the final executor for notes, calendar, search, settings, panels, and other local actions.

## What QMeet Can Do by Voice or Text

### General Commands

```text
what can you do
local tools
who are you
what did you hear
open menu
show menu
close menu
close panel
go home
clear chat
end chat
cancel
stop
never mind
```

### Settings and Voice Commands

```text
open settings
show settings
mute voice
unmute voice
voice off
voice on
toggle voice
speak slower
speak faster
normal voice
stop speaking
```

Voice output and speech speed are saved locally and should survive page reloads.

### Status Commands

```text
show status
system status
system dashboard
diagnostics
health check
show dashboard
what did you hear
```

The Status panel shows backend status, provider/model, voice input support, voice output state, speed, last heard transcript, last local command, command route, interpreter action/confidence, pending confirmation, chat status, notes count, and calendar event count.

### Notes Commands

```text
open notes
new note
take a note
write a note
note that buy milk
remember that test the tablet UI
save note call Dr. Fang
read my notes
show my notes
delete last note
remove last note
clear notes
close notes
```

Notes are stored in browser `localStorage` under:

```text
qmeet-notes
```

### Search Commands

```text
open search
open browser
search for raspberry pi kiosk mode
search the web for qmeet orb ui
web search qmeet orb ui
look up local voice assistant
look this up chromium flags
google chromium flags
find cats
clear search
close search
```

Search commands call the backend `/api/search` endpoint. The backend uses the configured provider to perform web search and returns structured results for the Search panel.

The Search panel shows:

```text
Summary
Recommended Setup / Recommendation
Action Steps
Useful Details
Sources
```

For search commands, the chat bubble stays short, for example:

```text
Search complete. I put the full result in the Search panel.
```

This prevents long web answers from becoming unreadable text walls in the chat panel.

### Calendar Commands

```text
open calendar
today
tomorrow
add event tomorrow at 3 called meeting
add event today at 5 called test tablet
add event today called QMeet test at 5
schedule meeting tomorrow at 3
remind me tomorrow at 3 to call bob
what's on my calendar
show today's events
show tomorrow's events
today's agenda
tomorrow's agenda
refresh calendar
sync calendar
reschedule last event to tomorrow at 4
move last event to today at 6
rename last event to edited QMeet test
change last event title to renamed event
edit last event to today at 6 called final edit test
delete last event
remove last event
clear calendar
clear calendar events
clear calander events
close calendar
```

Calendar behavior depends on whether Google Calendar is connected:

```text
Google Calendar connected
├─ read events from Google Calendar
├─ refresh/sync events on demand
├─ create events in Google Calendar after confirmation
├─ rename/reschedule/edit Google events after confirmation
├─ delete selected / last Google events after confirmation for voice/text commands
└─ show clear Google/local source labels in the Calendar panel

Google Calendar not connected
└─ fall back to local browser calendar events
```

Local fallback calendar events are stored in browser `localStorage` under:

```text
qmeet-calendar-events
```

`refresh calendar` / `sync calendar` reloads Google Calendar events from the backend without needing to close and reopen the panel.

`clear calendar` clears only local fallback events and local context. It does not mass-delete Google Calendar events. Google deletion is intentionally event-specific for safety.

Event editing is intentionally scoped to the selected/last event for now. QMeet asks for confirmation before changing the title, date, or time of a real Google Calendar event.

## Fuzzy Command Interpreter

QMeet includes a backend command interpreter for phrases that do not exactly match the frontend command parser.

Examples of fuzzy commands the interpreter can classify:

```text
wipe my calander stuff
pull up my notepad
don't talk out loud anymore
look up raspberry pi kiosk flags
put meeting on my calendar tomorrow at 3
what stuff do i have planned
```

The interpreter returns a strict result shaped like:

```json
{
  "intent": "command",
  "action": "clear_calendar",
  "confidence": 0.95,
  "frontendCommand": "clear calendar",
  "payload": {},
  "reason": "User requests to wipe calendar, interpreted as clear calendar."
}
```

The frontend then executes only known allowlisted commands. If the interpreter returns `intent: "chat"`, the message falls through to normal AI chat.

### Command Route Debugging

The Status panel shows how the most recent input was handled:

```text
Exact local command
Fuzzy interpreter command
Normal chat
```

For fuzzy interpreter commands, the Status panel also shows the interpreted action, confidence, mapped frontend command, and reason.

### Destructive Command Confirmation

Destructive local commands require confirmation before execution, whether they came from the exact parser or the fuzzy interpreter.

Protected commands include:

```text
clear chat
end chat
delete last note
clear notes
delete last event
clear calendar
```

Flow:

```text
User: wipe the calendar
QMeet: I understood that as: clear calendar. This changes or deletes local data. Say "confirm" to run it, or "cancel" to stop.
User: confirm
QMeet: Cleared all local calendar events.
```

Use `cancel`, `no`, or `never mind` to stop a pending destructive command.

## Recommended Development Flow

For normal development, run both the frontend and backend on the laptop.

```text
Browser frontend → Vite dev server → FastAPI backend → OpenAI
```

For Raspberry Pi testing, keep the laptop running the frontend/backend and open the laptop’s LAN URL from the Pi browser.

## Project Structure

```text
QMeet1-1/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app and routes
│   │   ├── agent.py            # OpenAI/mock provider logic, streaming, command interpreter, and web search
│   │   ├── calendar_service.py # Google Calendar OAuth/read/create/delete/edit helpers
│   │   └── schemas.py          # Request/response schemas, including command, search, and calendar schemas
│   ├── requirements.txt
│   ├── .env.example
│   └── .env                 # Must create locally using .env.example
│
├── src/
│   ├── app/
│   │   ├── App.tsx              # Main UI state/orchestration
│   │   ├── App.css              # Tablet UI styling
│   │   ├── api.ts               # Frontend API/SSE helpers
│   │   ├── commands.ts          # Local command parser/router definitions
│   │   ├── speechRecognition.ts # Browser speech-to-text helper
│   │   ├── speechSynthesis.ts   # Browser text-to-speech helper
│   │   ├── types.ts             # Shared frontend types
│   │   ├── utils.ts             # Frontend utilities
│   │   └── components/
│   │       ├── Orb.tsx
│   │       ├── TopStatusBar.tsx
│   │       ├── ChatPanel.tsx
│   │       ├── PromptBar.tsx
│   │       ├── NotesPanel.tsx
│   │       ├── CalendarPanel.tsx
│   │       └── SearchPanel.tsx
│   ├── styles/
│   │   ├── fonts.css
│   │   ├── globals.css
│   │   └── index.css
│   └── main.tsx
│
├── .env.local              # Frontend local config; do not commit
├── .gitignore
├── .gitattributes
├── ATTRIBUTIONS.md
├── index.html
├── package-lock.json
├── package.json
├── postcss.config.mjs
├── vite.config.ts
└── README.md
```

## Requirements

Frontend:

- Node.js
- npm

Backend:

- Python 3.10+
- FastAPI dependencies from `backend/requirements.txt`
- Google API client dependencies from `backend/requirements.txt` for Calendar integration
- OpenAI API key if using `LLM_PROVIDER=openai`
- Google OAuth credentials JSON if using Google Calendar

Browser features:

- Speech input uses the browser Web Speech API. Chrome/Chromium is the main target.
- Speech output uses browser `speechSynthesis`.
- Browser microphone permission must be enabled for voice input.
- Local Notes, Calendar fallback data, and voice settings use browser `localStorage`.

## Environment Setup

### Frontend `.env.local`

Create this file in the project root:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

For LAN testing from a Raspberry Pi or another device, use the laptop’s IP address:

```env
VITE_QMEET_API_URL=http://LAPTOP_IP:8000
```

Do **not** put an OpenAI API key in any `VITE_...` variable. Vite frontend environment variables are exposed to the browser.

### Backend `backend/.env`

Create this file inside `backend/`:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MAX_OUTPUT_TOKENS=300
FRONTEND_ORIGIN=http://localhost:5173
```

For mock mode:

```env
LLM_PROVIDER=mock
FRONTEND_ORIGIN=http://localhost:5173
```

For LAN testing, set `FRONTEND_ORIGIN` to the frontend URL being used by the browser if CORS blocks requests.

Example LAN backend `.env`:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MAX_OUTPUT_TOKENS=300
FRONTEND_ORIGIN=http://LAPTOP_IP:5173
```

### Google Calendar backend `.env`

For Google Calendar read/create/delete support, add these values to `backend/.env` after creating Google OAuth credentials:

```env
GOOGLE_CALENDAR_ENABLED=true
GOOGLE_CALENDAR_WRITE_ENABLED=true
GOOGLE_CALENDAR_CREDENTIALS_FILE=google_credentials.json
GOOGLE_CALENDAR_TOKEN_FILE=token_calendar_events.json
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8000/api/calendar/auth/callback
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=local
```

For local development, keep the Google OAuth redirect URI on `localhost` even if the Pi/tablet uses the backend over LAN. Authorize Google Calendar from the laptop once; after the token file is created, the Pi can use the already-authorized backend.

Required Google Calendar OAuth scopes:

```text
https://www.googleapis.com/auth/calendar.readonly
https://www.googleapis.com/auth/calendar.events
```

The OAuth client should include this exact redirect URI:

```text
http://localhost:8000/api/calendar/auth/callback
```

For a prototype, keep the app in Testing mode and add your Gmail account as a test user.

## Security Notes

Do not commit secret files.

Your `.gitignore` should include:

```gitignore
.env
.env.*
!.env.example

.env.local
.env.*.local

backend/.env
backend/.env.*
!backend/.env.example

backend/google_credentials.json
backend/token_calendar_readonly.json
backend/token_calendar_events.json
backend/calendar_auth_state.json

backend/.venv/
.venv/
node_modules/
dist/
__pycache__/
*.pyc
```

If an API key or Google OAuth credential/token file was ever pushed to GitHub, rotate/revoke it from the provider dashboard and replace it locally.

## Install and Run

### 1. Install frontend dependencies

From the project root:

```powershell
npm install
```

### 2. Start the backend

PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The backend should run at:

```text
http://localhost:8000
```

### 3. Start the frontend

Open another terminal from the project root:

```powershell
npm run dev
```

The frontend should run at:

```text
http://localhost:5173
```

Open that URL in Chrome/Chromium.

## LAN / Raspberry Pi Testing

Run the backend on all interfaces:

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run the frontend on all interfaces:

```powershell
npm run dev -- --host 0.0.0.0
```

On the Pi or tablet browser, open:

```text
http://LAPTOP_IP:5173
```

The frontend `.env.local` should point to:

```env
VITE_QMEET_API_URL=http://LAPTOP_IP:8000
```

The backend `FRONTEND_ORIGIN` should usually be:

```env
FRONTEND_ORIGIN=http://LAPTOP_IP:5173
```

## Backend Endpoints

```text
GET    /health
GET    /api/status
POST   /api/chat
POST   /api/chat/stream
POST   /api/command/interpret
POST   /api/reset

GET    /api/calendar/status
POST   /api/calendar/auth/start
GET    /api/calendar/auth/callback
POST   /api/calendar/auth/reset
GET    /api/calendar/events?view=today|tomorrow|week
POST   /api/calendar/events
PATCH  /api/calendar/events/{event_id}
DELETE /api/calendar/events/{event_id}
```

The frontend primarily uses `/api/chat/stream` for streamed responses, `/api/command/interpret` for fuzzy command classification, and the `/api/calendar/...` routes for Google Calendar read/create/delete/edit support.

## Basic Backend Tests

Health check:

```powershell
Invoke-RestMethod http://localhost:8000/health
```

Status check:

```powershell
Invoke-RestMethod http://localhost:8000/api/status
```

Non-streaming chat:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/chat" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"message":"What are you?"}'
```

Streaming chat:

```powershell
'{"message":"Give me one sentence about QMeet."}' | Set-Content -Encoding utf8 body.json

curl.exe -N -X POST "http://localhost:8000/api/chat/stream" `
  -H "Content-Type: application/json" `
  -H "Accept: text/event-stream" `
  --data-binary "@body.json"

Remove-Item body.json
```


Command interpreter test:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/command/interpret" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"message":"wipe my calander stuff"}'
```

Expected shape:

```text
intent          : command
action          : clear_calendar
confidence      : 0.95
frontendCommand : clear calendar
```

Calendar status:

```powershell
Invoke-RestMethod http://localhost:8000/api/calendar/status
```

Calendar read:

```powershell
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=today"
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=tomorrow"
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=week"
```

Start Google OAuth authorization:

```powershell
$auth = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/calendar/auth/start" `
  -Method POST

Start-Process $auth.authUrl
```

Create a Google Calendar event:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/calendar/events" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"title":"QMeet test event","day":"tomorrow","time":"3 PM"}'
```

Edit/reschedule a Google Calendar event after fetching one:

```powershell
$events = Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=today"
$eventId = $events.events[0].googleEventId

Invoke-RestMethod `
  -Uri "http://localhost:8000/api/calendar/events/$eventId" `
  -Method PATCH `
  -ContentType "application/json" `
  -Body '{"title":"Updated QMeet test event","day":"tomorrow","time":"4 PM"}'
```

Delete a Google Calendar event after fetching one:

```powershell
$events = Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=today"
$eventId = $events.events[0].googleEventId

Invoke-RestMethod `
  -Uri "http://localhost:8000/api/calendar/events/$eventId" `
  -Method DELETE
```

## Web Search Backend Test

After the backend is running, test the search endpoint directly:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/search" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"query":"raspberry pi chromium kiosk mode"}'
```

Expected response shape:

```text
ok             : True
query          : raspberry pi chromium kiosk mode
summary        : ...
recommendation : ...
actionSteps    : {...}
detailCards    : {...}
sources        : {...}
provider       : openai
message        : Search complete.
```

Search requires the backend provider to support web search. In mock mode, QMeet returns a mock search response.

## Build

```powershell
npm run build
npm run preview
```

## Current Interaction Flow

### Normal AI prompt

```text
User types or speaks a prompt
↓
Frontend checks exact local commands first
↓
No exact command match
↓
Frontend asks backend command interpreter for strict JSON classification
↓
Interpreter returns intent = chat
↓
Prompt streams through FastAPI/OpenAI
↓
Thinking bubble appears until first token arrives
↓
Assistant message streams into chat
↓
Orb speaks completed response if voice output is enabled
```

### Local command

```text
User types or speaks a local command
↓
Exact command parser matches locally
↓
No normal OpenAI chat request is made
↓
UI action runs immediately
↓
Assistant confirmation appears
↓
Orb speaks confirmation if voice output is enabled
```

### Fuzzy interpreted command

```text
User types or speaks a command with unusual wording or speech-recognition mistakes
↓
Exact command parser does not match
↓
Backend command interpreter classifies the phrase into strict JSON
↓
Frontend checks the mapped command against its allowlist
↓
If safe and confident, frontend executes the local action
↓
Normal chat is skipped
```

### Destructive command confirmation

```text
User asks for a destructive local command
↓
QMeet stores a pending command instead of executing immediately
↓
User says confirm / yes / do it
↓
Frontend executes the pending command

or

User says cancel / no / never mind
↓
Pending command is discarded
```

### Web search command

```text
User asks QMeet to search for something
↓
Exact command parser maps the phrase to a search command
↓
Frontend calls FastAPI /api/search
↓
Backend performs web search through the configured provider
↓
Backend returns structured search data
↓
Search panel renders Summary, Recommendation, Action Steps, Useful Details, and Sources
↓
Chat bubble only shows a short completion message
```

Search output is intentionally kept out of the main chat stream so long web results stay readable on the 1024×600 tablet UI.

### Google Calendar command

```text
User asks for calendar read/create/edit/delete
↓
Frontend command parser or fuzzy interpreter maps the phrase
↓
For create/edit/delete, QMeet asks for confirmation
↓
Frontend calls FastAPI calendar endpoint
↓
Backend uses saved Google OAuth token
↓
Google Calendar read/create/edit/delete runs
↓
QMeet refreshes calendar events and reports the real backend result

For refresh/sync commands, QMeet reloads Google Calendar events without creating or deleting anything.
```

### Voice input

```text
User taps orb
↓
Orb enters listening state
↓
Listening transcript preview appears
↓
Final transcript is normalized
↓
QMeet checks the exact local command parser
↓
If needed, QMeet asks the fuzzy command interpreter
↓
Command runs locally or prompt streams through backend chat
```

### Cancel / stop behavior

```text
Tap orb while QMeet is thinking or streaming
↓
Active response is cancelled
↓
Orb returns to idle

Tap orb while QMeet is speaking
↓
Speech stops
↓
Orb returns to idle
```

## Local Storage Keys

QMeet currently stores local frontend state in browser `localStorage`.

```text
qmeet-notes
qmeet-calendar-events
qmeet-voice-output-enabled
qmeet-speech-rate
```

These are browser-local. Clearing site data or using a different browser/device will remove or hide the saved local fallback data.

Google Calendar OAuth tokens are backend-local files, not browser localStorage:

```text
backend/token_calendar_events.json
```

## Voice Settings

Voice output is controlled locally in the frontend.

Supported commands include:

```text
mute voice
unmute voice
voice off
voice on
toggle voice
speak slower
speak faster
normal voice
stop speaking
```

The Settings panel also exposes controls for spoken responses and speech speed.

Voice output enabled/disabled and speech speed are saved to `localStorage`.

## Troubleshooting

### Backend shows disconnected

Check that the backend is running:

```powershell
Invoke-RestMethod http://localhost:8000/api/status
```

Check `.env.local`:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

For LAN testing, use the laptop IP instead of `localhost`.

### Web search works but results look shallow

Try a more specific query. For example:

```text
search for raspberry pi chromium kiosk mode systemd autostart 1024x600
```

The backend prompt asks for action-oriented output, but very broad queries may still produce generic summaries.

### Web search fails

Check the backend search endpoint directly:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/search" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"query":"OpenAI web search Responses API"}'
```

If this fails, verify:

```text
backend/.env has OPENAI_API_KEY
backend/.env has LLM_PROVIDER=openai
backend is running on port 8000
frontend .env.local points to the backend URL
```

### Search panel shows old placeholder behavior

Make sure these files were updated together:

```text
backend/app/agent.py
backend/app/schemas.py
src/app/types.ts
src/app/App.tsx
src/app/components/SearchPanel.tsx
```

Then restart both backend and frontend.

### Google Calendar is not connected

Check backend calendar status:

```powershell
Invoke-RestMethod http://localhost:8000/api/calendar/status
```

Expected when connected:

```text
configured : True
connected  : True
writeEnabled : True
```

If disconnected, check that `backend/.env` points to the correct token file and that the token exists:

```powershell
cd backend
dir token_calendar_events.json
```

If needed, reset and re-authorize:

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/calendar/auth/reset" `
  -Method POST

$auth = Invoke-RestMethod `
  -Uri "http://localhost:8000/api/calendar/auth/start" `
  -Method POST

Start-Process $auth.authUrl
```

Use `localhost` for Google OAuth authorization from the laptop. Do not use a raw LAN IP as an OAuth origin or redirect URI.

### Google Calendar OAuth says the app is not verified

For prototype development, keep the Google app in Testing mode and add your Gmail as a test user:

```text
Google Cloud Console
└─ Google Auth Platform / OAuth consent screen
   ├─ Audience
   │  ├─ Publishing status: Testing
   │  └─ Test users: your Gmail
   └─ Data Access
      ├─ https://www.googleapis.com/auth/calendar.readonly
      └─ https://www.googleapis.com/auth/calendar.events
```

### Google Calendar scope changed / PKCE errors

If authorization fails after changing scopes, reset auth and start from a fresh auth URL. The backend stores temporary OAuth state in:

```text
backend/calendar_auth_state.json
```

That file should not be committed. It is temporary and can be removed before retrying OAuth if the flow gets stuck.

### Calendar creates an all-day event when you expected a time

QMeet creates a timed event only when the parser extracts a time such as `5`, `5:00`, `3 PM`, or `at 3`. Good test phrases:

```text
add event today at 5 called QMeet test
add event today called QMeet test at 5
add event tomorrow at 3 PM called meeting
```

If the confirmation reads the wrong title or time, say `cancel` and rephrase before confirming.

### Microphone does not work

- Use Chrome/Chromium.
- Allow microphone permission in the browser.
- Check that the site is loaded from `localhost` or a trusted LAN context.
- Tap the orb again after changing permissions.

### QMeet does not recognize its name

The command parser normalizes common speech-recognition variants such as:

```text
queue meet
cue meet
cute meet
queue meat
cue meat
key meet
```

If the browser produces a new misheard variant, add it to `normalizeSpokenQMeet()` in `src/app/commands.ts`.

### A local command goes to OpenAI instead

The exact command parser and fuzzy command interpreter did not classify the text as a local command, so the prompt fell through to backend chat.

Check:

```text
what did you hear
```

Then check the Status panel to see whether the last route was:

```text
Exact local command
Fuzzy interpreter command
Normal chat
```

If the exact parser should handle the phrase, add a pattern in:

```text
src/app/commands.ts
```

If the interpreter misunderstood the phrase, update the backend interpreter prompt/schema/mapping in:

```text
backend/app/agent.py
backend/app/schemas.py
src/app/App.tsx
```

For common misspellings, aliases can still be added to the exact parser. Example: the calendar clear command currently accepts variants such as `calendar`, `calender`, and `calander`.

### QMeet asks for confirmation before clearing or deleting

This is expected for destructive local commands. Say:

```text
confirm
```

To stop the pending action, say:

```text
cancel
never mind
no
```

### Calendar events are remembered but not visible

For Google Calendar events, first check that the backend is connected and reading events:

```powershell
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=today"
Invoke-RestMethod "http://localhost:8000/api/calendar/events?view=tomorrow"
```

For local fallback events, data may exist in localStorage but the visible panel can hide events if the event date key does not match the current Today/Tomorrow view.

Try:

```text
what's on my calendar
show today's events
show tomorrow's events
open calendar
today
tomorrow
```

The current build includes fixes so old UTC-style date keys and current local date keys should both display correctly.

### QMeet says a calendar event was deleted but it still exists

This should not happen for the current Google Calendar delete path. Confirm backend connectivity first:

```powershell
Invoke-RestMethod http://localhost:8000/api/calendar/status
```

If the frontend was pointing to an old LAN IP in `.env.local`, it may not have been talking to the backend you expected. For same-laptop testing, use:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

Restart Vite after changing `.env.local`.

### QMeet cannot update or reschedule a Google Calendar event

Check that Google Calendar is still connected and that the frontend is talking to the correct backend:

```powershell
Invoke-RestMethod http://localhost:8000/api/calendar/status
```

For same-laptop testing, `.env.local` should use:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

If creation works but rescheduling fails, restart the backend and confirm the current calendar service patch is loaded. The current edit path avoids sending invalid local timezone strings when `GOOGLE_CALENDAR_TIMEZONE=local`.

### QMeet remembers old calendar events after clearing

Use one of the local clear commands:

```text
clear calendar
clear calendar events
clear calander events
clear my schedule
```

The local clear command clears only `qmeet-calendar-events` and resets backend conversation context so OpenAI does not repeat stale local events from chat memory. It does not mass-delete Google Calendar events.

### Voice output does not work

- Check that browser audio is not muted.
- Try the command `unmute voice`.
- Try `normal voice` to reset speed.
- Speech output uses the browser `speechSynthesis` API, so behavior can vary by browser and OS.

### Saved notes/calendar/settings disappeared

These are stored in browser `localStorage`.

They can disappear if:

- Browser site data is cleared
- A different browser is used
- A different LAN URL/origin is used
- Chrome profile changes
- Incognito/private mode is used

### PowerShell blocks npm scripts

If PowerShell blocks npm scripts, either use Command Prompt/Git Bash or set execution policy for the current user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Development Notes

- Keep the frontend OpenAI-key-free. API keys belong only in `backend/.env`.
- Exact local commands should run before the fuzzy command interpreter.
- The fuzzy command interpreter should run before normal chat.
- The command interpreter should return strict JSON only.
- The command interpreter should never directly mutate frontend state.
- Frontend command execution should remain allowlisted and deterministic.
- Destructive local commands should require confirmation.
- Local command responses should not call normal OpenAI chat.
- Notes, Calendar, Settings, Status, and Menu should remain usable without normal OpenAI chat. Search should use the dedicated backend search endpoint instead of normal chat.
- Google Calendar credentials and tokens must stay backend-only and ignored by git.
- Calendar create/delete actions should keep confirmation or explicit user intent.
- `clear calendar` should remain local-only unless a separate, heavily confirmed Google bulk-delete feature is intentionally added.
- The UI is currently optimized for the 1024×600 tablet target.
- Pi kiosk/autolaunch work is intentionally delayed until the prototype is more complete.
- Search results should stay structured and readable on the 1024×600 tablet target.


### Calendar refresh does not show new events

Use one of these commands:

```text
refresh calendar
sync calendar
```

Or open the Calendar panel and use the refresh button. This reloads Google Calendar events from the backend. If refresh still shows stale data, verify the backend is connected:

```powershell
Invoke-RestMethod http://localhost:8000/api/calendar/status
```

Expected:

```text
connected : True
```

## Current Status

Completed prototype phases:

- Phase 1: Browser voice input
- Phase 2: Local UI command routing
- Phase 3: Browser voice output
- Phase 4A: Voice output settings
- Phase 4B: Tablet panels and launcher
  - Notes panel
  - Calendar panel
  - Search/browser placeholder panel
  - Menu launcher
  - Status dashboard
  - Home behavior polish
- Phase 4C: Command diagnostics / “what did you hear?”
- Phase 4D: Cancel/stop behavior and listening transcript preview
- Phase 4E-1: Voice notes
- Phase 4E-2: Voice search placeholder
- Phase 4E-3: Local voice calendar
- Phase 4F-1: Persistent voice settings
- Phase 4F-2: Local tool polish
- Calendar bug fixes:
  - visual event display after reload
  - clear calendar command aliases
  - backend reset after local calendar clear
- Phase 5A: Backend fuzzy command interpreter
- Phase 5B: Command route/status debugging
- Phase 5C: Confirmation for destructive local commands
- Phase 6A: Google Calendar read integration
- Phase 6B: Google Calendar event creation
- Phase 6C: Google Calendar event deletion
- Phase 6D: Calendar polish
  - refresh/sync calendar command
  - safer delete confirmation with event title/time
  - panel delete browser confirmation
  - clearer Google/local source labels
  - cleaner event sorting
- Phase 6E: Google Calendar event editing
  - rename last event
  - reschedule last event
  - edit last event title/date/time together
  - confirmation before changing real Google Calendar events
  - timezone fix for rescheduling when using local timezone config
- Phase 7A: Real web search integration
  - backend `/api/search` endpoint
  - OpenAI web search through the backend
  - voice/text search command execution
  - Search panel result state
- Phase 7B/7D: Search presentation and usefulness polish
  - structured search response data
  - summary, recommendation, action steps, useful details, and sources
  - short chat acknowledgement instead of full search wall
- Phase 7E/7F: Search readability and formatting polish
  - cleaner action steps
  - cleaned source cards
  - markdown/artifact cleanup
  - better readable result layout on the tablet screen
- Calendar parser fixes:
  - title-before-time event phrasing
  - speech artifacts such as `to at 5`
  - prevents `today`/`tomorrow` from being treated as event time
- Orb listening/processing state fix

Useful future work:

- Add richer source ranking / domain grouping for Search
- Add search result history or saved search cards
- Add follow-up search commands such as “open the first source” later
- Add command interpreter test coverage / command audit logs
- Add Google Calendar edit/delete-by-title/date matching
- Add safer event disambiguation when multiple matching events exist
- Add richer date parsing beyond today/tomorrow
- Add edit/search/delete-by-name for notes
- Improve Settings/Menu/Status visual design
- Add persistent UI preferences beyond voice settings
- Add optional wake-word-style behavior later
- Add Pi kiosk/autostart once the prototype is closer to complete
- Consider backend/local TTS later if browser speech is not good enough
