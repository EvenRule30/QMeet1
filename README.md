# QMeet1-1

QMeet is a React/Vite prototype for a tablet-style AI home screen. The interface centers on an animated AI orb that can listen, answer, speak aloud, and control local UI panels through voice or typed commands.

The current prototype is designed around a **1024×600 landscape Raspberry Pi/tablet display**, and is currently configured to work with Google Chrome browser browser.

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
- Menu, Settings, and Status panels
- Voice output settings, including mute/unmute and speech speed control
- Local command help: asking what QMeet can do explains available voice commands
- QMeet name recognition normalization for common speech parser mistakes such as “cue meet,” “queue meet,” or “cute meet”
- Conversation reset and backend memory reset
- Laptop-to-Raspberry-Pi LAN testing

## What QMeet Can Do by Voice or Text

The local command router handles simple commands directly in the frontend. These commands do **not** call OpenAI.

Examples:

```text
what can you do
who are you
open menu
show menu
open settings
show settings
show status
close menu
close settings
close status
close panel
go home
clear chat
end chat
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

Normal prompts that do not match a local command are sent to the backend AI provider.

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
│   └── .env                 # Must add yourself using template from .env.example
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
│   │       └── PromptBar.tsx
│   ├── styles/
|   |   ├── fonts.css
│   │   ├── globals.css
│   │   ├── index.css
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

## Voice Settings

Voice output is currently controlled locally in the frontend.

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

### Voice output does not work

- Check that browser audio is not muted.
- Try the command `unmute voice`.
- Try `normal voice` to reset speed.
- Speech output uses the browser `speechSynthesis` API, so behavior can vary by browser and OS.

### PowerShell blocks npm scripts

If PowerShell blocks npm scripts, either use Command Prompt/Git Bash or set execution policy for the current user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Development Notes

- Keep the frontend OpenAI-key-free. API keys belong only in `backend/.env`.
- Local commands should run before sending prompts to the backend.
- Local command responses should not call OpenAI.
- The UI is currently optimized for the 1024×600 tablet target.
- Pi kiosk/autolaunch work is intentionally delayed until the prototype is more complete.

## Current Status

Completed prototype phases:

- Phase 1: Browser voice input
- Phase 2: Local UI command routing
- Phase 3: Browser voice output
- Phase 4A: Voice output settings
- QoL: cleaner thinking bubble behavior
- QoL: QMeet name normalization for speech parser mistakes

Useful future work:

- Add more real tablet commands and app panels
- Improve Settings/Menu/Status visual design
- Add persistent settings with `localStorage`
- Add optional wake-word-style behavior later
- Add Pi kiosk/autostart once the prototype is closer to complete
- Consider backend/local TTS later if browser speech is not good enough
