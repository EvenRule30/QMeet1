# QMeet1-1

QMeet is a React/Vite prototype for a tablet-style AI home screen. The interface centers on an animated AI orb that can listen, answer, speak aloud, and control local tablet panels through voice or typed commands.

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
- Menu launcher panel
- Settings panel
- Status/system dashboard panel
- Local Notes panel with `localStorage` persistence
- Voice note creation, reading, deleting, and clearing
- Local Search/Browser placeholder panel
- Voice search query preparation without real web integration yet
- Local Calendar panel with `localStorage` event persistence
- Voice calendar event creation, reading, deleting, and clearing
- Persistent voice output settings across reloads
- Persistent speech speed across reloads
- Voice output settings, including mute/unmute and speech speed control
- Local command help: asking what QMeet can do explains available voice commands
- “What did you hear?” voice debugging
- QMeet name recognition normalization for common speech parser mistakes such as “cue meet,” “queue meet,” or “cute meet”
- Cancel/stop behavior for speech, listening, and active streamed responses
- Conversation reset and backend memory reset
- Laptop-to-Raspberry-Pi LAN testing

## What Runs Locally vs Through OpenAI

QMeet checks local commands first. If the command parser matches the text, the action runs entirely in the frontend and **does not call OpenAI**.

Examples of local-only actions:

- Opening panels
- Saving notes
- Reading saved notes
- Preparing a search query
- Adding local calendar events
- Reading local calendar events
- Muting/unmuting voice output
- Changing voice speed
- Going home
- Clearing local UI state

Normal prompts that do not match a local command are sent to the FastAPI backend, which then uses the configured AI provider.

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

The Status panel shows backend status, provider/model, voice input support, voice output state, speed, last heard transcript, last local command, chat status, notes count, and calendar event count.

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

Search is currently a local placeholder. It opens the Search panel and fills/prepares the query, but does not perform real web browsing yet.

### Calendar Commands

```text
open calendar
today
tomorrow
add event tomorrow at 3 called meeting
add event today at 5 called test tablet
schedule meeting tomorrow at 3
remind me tomorrow at 3 to call bob
what's on my calendar
show today's events
show tomorrow's events
today's agenda
tomorrow's agenda
delete last event
remove last event
clear calendar
clear calendar events
clear calander events
close calendar
```

Calendar events are stored in browser `localStorage` under:

```text
qmeet-calendar-events
```

The calendar is currently local-only. It is not connected to Google Calendar yet.

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
│   │   ├── agent.py         # OpenAI/mock provider logic and streaming
│   │   └── schemas.py       # Request/response schemas
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
- OpenAI API key if using `LLM_PROVIDER=openai`

Browser features:

- Speech input uses the browser Web Speech API. Chrome/Chromium is the main target.
- Speech output uses browser `speechSynthesis`.
- Browser microphone permission must be enabled for voice input.
- Local Notes, Calendar, Search state, and voice settings use browser `localStorage`.

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

backend/.venv/
.venv/
node_modules/
dist/
__pycache__/
*.pyc
```

If an API key was ever pushed to GitHub, rotate it from the provider dashboard and replace it locally.

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
GET  /health
GET  /api/status
POST /api/chat
POST /api/chat/stream
POST /api/reset
```

The frontend primarily uses `/api/chat/stream` for streamed responses.

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
Frontend checks local commands first
↓
No command match
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
Command parser matches locally
↓
No OpenAI request is made
↓
UI action runs immediately
↓
Assistant confirmation appears
↓
Orb speaks confirmation if voice output is enabled
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
QMeet checks local command parser
↓
Command runs locally or prompt streams through backend
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

These are browser-local. Clearing site data or using a different browser/device will remove or hide the saved local data.

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

The command parser did not match the text, so the prompt fell through to backend chat.

Check:

```text
what did you hear
```

Then add a matching pattern in:

```text
src/app/commands.ts
```

For common misspellings, add aliases. Example: the calendar clear command currently accepts variants such as `calendar`, `calender`, and `calander`.

### Calendar events are remembered but not visible

Calendar data may exist in localStorage but the visible panel can hide events if the event date key does not match the current Today/Tomorrow view.

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

### QMeet remembers old calendar events after clearing

Use one of the local clear commands:

```text
clear calendar
clear calendar events
clear calander events
clear my schedule
```

The local clear command should clear `qmeet-calendar-events` and reset backend conversation context so OpenAI does not repeat stale events from chat memory.

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
- Local commands should run before sending prompts to the backend.
- Local command responses should not call OpenAI.
- Notes, Calendar, Search, Settings, Status, and Menu should remain usable without OpenAI.
- The UI is currently optimized for the 1024×600 tablet target.
- Pi kiosk/autolaunch work is intentionally delayed until the prototype is more complete.
- Real web search and Google Calendar integration are not implemented yet.

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

Useful future work:

- Add real web/browser integration for Search
- Add Google Calendar integration
- Add edit/search/delete-by-name for notes and calendar events
- Improve Settings/Menu/Status visual design
- Add persistent UI preferences beyond voice settings
- Add optional wake-word-style behavior later
- Add Pi kiosk/autostart once the prototype is closer to complete
- Consider backend/local TTS later if browser speech is not good enough
