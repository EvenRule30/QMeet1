# QMeet Architecture Snapshot

This document describes the current QMeet architecture after the Phase 9G refactor arc.

## High-level architecture

```text
User
├─ taps/types/speaks into React UI
│
Frontend
├─ Orb and chat interface
├─ command parser and fuzzy command interpreter client
├─ panels for notes, memory, calendar, search, settings, status, menu
├─ hooks for backend status, memory, search, calendar, speech, chat streaming
└─ API client for FastAPI
│
Backend
├─ FastAPI app
├─ feature routers
├─ OpenAI chat/search/command interpreter service
├─ Google Calendar service
└─ local JSON memory store
│
External services
├─ OpenAI API
└─ Google Calendar API
```

## Frontend responsibilities

The frontend owns the tablet user experience. It handles visual state, orb state, panel state, speech recognition, speech synthesis, streaming response display, and local command execution.

```text
src/app/
├─ App.tsx
│  └─ top-level orchestration and remaining command flow
├─ api.ts
│  └─ typed client for FastAPI endpoints
├─ commands.ts
│  └─ exact local command parser
├─ types.ts
│  └─ shared frontend request/response/UI types
├─ hooks/
│  └─ feature state controllers
├─ commandHandlers/
│  └─ command execution branches grouped by feature
├─ lib/
│  └─ pure helper utilities
├─ panels/
│  └─ overlay wrappers for panel UI
└─ components/
   └─ reusable UI components
```

## Important frontend hooks

```text
useBackendStatus
└─ polls /api/status and exposes backend connection state

useResultToasts
└─ owns command/result toast list, dismissal, and auto-timeouts

useMemoryContext
├─ loads backend memory context
├─ syncs tasks, notes, and recent actions
├─ keeps localStorage fallback active
├─ handles memory import/export/reset controls
└─ exposes memory and note actions

useSearchController
├─ owns search query/result/loading/error state
└─ runs and clears web searches

useCalendarController
├─ owns local calendar state
├─ owns Google Calendar state/status/error/loading
├─ handles Google auth start/reset
├─ reads Google Calendar events
└─ creates/edits/deletes calendar events

useSpeechOutput
├─ owns voice output enabled state
├─ owns speech rate state
├─ persists voice settings
└─ speaks/stops assistant text

useChatStreamController
├─ owns chat messages
├─ owns streaming abort state
├─ sends normal streaming chat
└─ cancels active responses

useSpeechRecognitionController
├─ starts browser speech recognition
├─ manages listening transcript preview
├─ handles silence timeout
├─ handles microphone/browser errors
└─ sends final transcript to App command routing
```

## Command flow

QMeet has two command layers.

```text
Exact parser
└─ src/app/commands.ts
   ├─ fast local command matching
   └─ handles known command phrases directly

Fuzzy interpreter
└─ backend /api/command/interpret
   ├─ OpenAI or mock interpreter
   ├─ maps fuzzy natural language to exact frontend commands
   └─ returns confidence and frontendCommand
```

Execution is split into command handler files:

```text
src/app/commandHandlers/
├─ notes.ts
├─ memory.ts
├─ search.ts
├─ voice.ts
└─ calendar.ts
```

`App.tsx` still owns the main orchestration path: command detection, confirmation prompts, destructive-command safety checks, and normal-chat fallback.

## Backend responsibilities

The backend owns LLM calls, web search, Google Calendar integration, persistent memory storage, and API routing.

```text
backend/app/
├─ main.py
│  └─ app setup, CORS, router includes
├─ routers/
│  ├─ chat.py
│  ├─ command.py
│  ├─ search.py
│  ├─ calendar.py
│  └─ memory.py
├─ agent.py
│  └─ chat, streaming, command interpreter, and web search helper logic
├─ calendar_service.py
│  └─ Google OAuth and Calendar API behavior
├─ memory_store.py
│  └─ local JSON memory persistence
└─ schemas.py
   └─ Pydantic request/response models
```

## Backend routes

```text
Core
├─ GET  /health
└─ GET  /api/status

Chat
├─ POST /api/chat
├─ POST /api/chat/stream
└─ POST /api/reset

Command interpreter
└─ POST /api/command/interpret

Search
└─ POST /api/search

Calendar
├─ GET    /api/calendar/status
├─ POST   /api/calendar/auth/start
├─ GET    /api/calendar/auth/callback
├─ POST   /api/calendar/auth/reset
├─ GET    /api/calendar/events
├─ POST   /api/calendar/events
├─ PATCH  /api/calendar/events/{event_id}
└─ DELETE /api/calendar/events/{event_id}

Memory
├─ GET    /api/memory/status
├─ GET    /api/memory/context
├─ PUT    /api/memory/context
├─ GET    /api/memory/export
├─ POST   /api/memory/import
├─ POST   /api/memory/clear
├─ GET    /api/memory/tasks
├─ PUT    /api/memory/tasks
├─ POST   /api/memory/tasks
├─ PATCH  /api/memory/tasks/{task_id}
├─ DELETE /api/memory/tasks/{task_id}
├─ POST   /api/memory/tasks/clear-completed
├─ GET    /api/memory/notes
├─ PUT    /api/memory/notes
├─ POST   /api/memory/notes
├─ DELETE /api/memory/notes/{note_id}
├─ POST   /api/memory/notes/clear
├─ GET    /api/memory/actions
├─ PUT    /api/memory/actions
├─ POST   /api/memory/actions
├─ DELETE /api/memory/actions/{action_id}
└─ POST   /api/memory/actions/clear
```

## Memory model

The backend memory store keeps three main categories:

```text
backend/data/qmeet_memory.json
├─ tasks
├─ notes
└─ recentActions
```

The frontend treats backend memory as primary and browser localStorage as fallback. This lets the Raspberry Pi frontend and laptop frontend share the same backend memory when pointed at the same FastAPI server.

## Deployment notes

The app is still a prototype. For future deployment, likely next improvements are:

```text
├─ environment validation on backend startup
├─ production CORS tightening
├─ more robust memory storage than local JSON
├─ Pi startup service hardening
├─ frontend error boundary
├─ automated endpoint tests
└─ calendar-aware chat context
```
