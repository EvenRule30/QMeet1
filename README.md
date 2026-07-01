# QMeet — AI Tablet Interface

QMeet is a dark-mode AI tablet interface built with **React + Vite** and a **FastAPI AI backend**.

**Target:** Raspberry Pi 7" tablet at **1024×600 landscape**.

The current prototype supports:

- Animated orb assistant UI
- Chat panel and prompt bar
- FastAPI backend
- OpenAI model responses
- Mock provider fallback
- Backend status display
- Conversation reset
- SSE streaming responses
- LAN testing from Raspberry Pi to laptop-hosted frontend/backend

## Getting Started

### Frontend

```bash
npm install
npm run dev
```

The frontend runs at:

```text
http://localhost:5173
```

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The backend runs at:

```text
http://localhost:8000
```

## Environment Setup

### Frontend `.env.local`

Create this in the project root:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

For LAN testing, use the laptop/backend IP:

```env
VITE_QMEET_API_URL=http://LAPTOP_IP:8000
```

### Backend `backend/.env`

Create this inside `backend/`:

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=your_real_api_key_here
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MAX_OUTPUT_TOKENS=300
FRONTEND_ORIGIN=http://localhost:5173
```

For mock mode:

```env
LLM_PROVIDER=mock
```

Do **not** commit `.env` files.

## Project Structure

```text
src/
├── app/
│   ├── App.tsx
│   ├── App.css
│   ├── api.ts
│   ├── types.ts
│   ├── utils.ts
│   └── components/
│       ├── Orb.tsx
│       ├── TopStatusBar.tsx
│       ├── ChatPanel.tsx
│       └── PromptBar.tsx
├── styles/
│   ├── index.css
│   ├── globals.css
│   └── fonts.css
└── main.tsx

backend/
├── app/
│   ├── main.py
│   ├── agent.py
│   └── schemas.py
├── requirements.txt
└── .env.example
```

## Architecture

```text
QMeet frontend
   ↓
FastAPI backend
   ↓
LLM provider
   ├── OpenAI
   └── Mock fallback
```

Main backend endpoints:

```text
GET  /health
GET  /api/status
POST /api/chat
POST /api/chat/stream
POST /api/reset
```

## Interaction Flow

1. **Idle** — Orb centered, waiting for user input.
2. **Thinking** — Prompt sent to backend.
3. **Speaking** — Streaming response appears in chat.
4. **Idle** — Response complete.
5. **End Chat** — Frontend clears messages and backend resets conversation memory.

## LAN Prototype

The current working Raspberry Pi test uses the laptop as the server.

On the laptop:

```powershell
# Backend
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

```powershell
# Frontend
npm run dev -- --host 0.0.0.0
```

On the Raspberry Pi, open:

```text
http://LAPTOP_IP:5173
```

The Pi should load the QMeet UI, show the backend as connected, and receive GPT responses through the laptop backend.

## Testing

### Backend health

```powershell
Invoke-RestMethod http://localhost:8000/health
```

### Backend status

```powershell
Invoke-RestMethod http://localhost:8000/api/status
```

### Non-streaming chat

```powershell
Invoke-RestMethod `
  -Uri "http://localhost:8000/api/chat" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"message":"What are you?"}'
```

### Streaming chat

```powershell
'{"message":"Give me one sentence about QMeet."}' | Set-Content -Encoding utf8 body.json

curl.exe -N -X POST "http://localhost:8000/api/chat/stream" `
  -H "Content-Type: application/json" `
  -H "Accept: text/event-stream" `
  --data-binary "@body.json"

Remove-Item body.json
```

## Build

```bash
npm run build
npm run preview
```

## Development Notes

- The UI is designed around a fixed 1024×600 tablet layout.
- Styling is plain CSS.
- No React Router, Recharts, Tailwind, MUI, or shadcn/ui bloat.
- OpenAI keys stay in the backend only.
- `.venv`, `node_modules`, `.env`, `__pycache__`, and `dist` should not be committed.

## Current Status

Working:

- React tablet UI
- FastAPI backend
- OpenAI responses
- Mock fallback
- Backend status polling
- Conversation reset
- SSE streaming
- Raspberry Pi LAN test through laptop frontend/backend

Not yet implemented:

- Ollama provider
- Voice input
- Voice output
- Persistent chat storage
- Pi kiosk/autolaunch mode

## Browser Support

Modern browsers only: Chrome, Firefox, Safari, and Edge.
