# QMeet Architecture Snapshot

This document describes the current QMeet architecture after Phase 12E. QMeet is a voice-first React/FastAPI prototype centered on an on-screen orb assistant, persistent memory, Google Calendar, web search, and Active Context / Focus Sessions.

## High-level architecture

```text
User
├─ taps/types/speaks into React UI
│
Frontend
├─ Orb and chat interface
├─ exact command parser
├─ backend fuzzy command interpreter client
├─ panels for notes, memory, calendar, search, settings, status, menu
├─ Active Focus Session display and state bridge
├─ hooks for backend status, memory, search, calendar, speech, chat streaming
└─ typed API client for FastAPI
│
Backend
├─ FastAPI app
├─ feature routers
├─ OpenAI chat/search/command interpreter service
├─ deterministic focus command routing helpers
├─ Google Calendar service
└─ local JSON memory store
│
External services
├─ OpenAI API
└─ Google Calendar API
```

## Frontend responsibilities

The frontend owns the tablet user experience. It handles visual state, orb state, panel state, speech recognition, speech synthesis, streaming response display, local command execution, focus-session state display, and browser fallback memory.

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
├─ syncs tasks, notes, recent actions, and activeSession
├─ keeps localStorage fallback active
├─ handles memory import/export/reset controls
├─ listens for active-session state events
└─ exposes memory, note, task, and focus-session actions

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
├─ injects neutral active-focus context into chat
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
   ├─ handles known command phrases directly
   └─ catches focus/session/task/note/search/calendar/voice UI commands

Fuzzy interpreter
└─ backend /api/command/interpret
   ├─ deterministic focus routing helpers for common focus phrases
   ├─ OpenAI or mock interpreter fallback
   ├─ maps fuzzy natural language to exact frontend commands
   └─ returns confidence and frontendCommand
```

Execution is split into command handler files:

```text
src/app/commandHandlers/
├─ calendar.ts
├─ memory.ts
├─ notes.ts
├─ search.ts
└─ voice.ts
```

`App.tsx` still owns the main orchestration path: command detection, confirmation prompts, destructive-command safety checks, feature-handler dispatch, and normal-chat fallback.

## Active Context / Focus Session flow

Active Focus Sessions are the Phase 12 context engine foundation.

```text
User phrase
├─ start/update/read/end focus command
├─ focus-to-tasks command
├─ focus summary/save/end command
└─ normal chat prompt referring to current focus

Frontend parser/backend router
└─ maps phrase to local frontend command when it should mutate memory

memory command handler
├─ writes activeSession/tasks/notes through useMemoryContext and API helpers
├─ mirrors activeSession into browser storage for immediate UI readback
└─ opens Memory or Notes depending on the result

TopStatusBar / Memory panel
└─ display current focus state

Chat stream hook
└─ includes neutral active-focus context for normal chat prompts
```

Active session shape:

```ts
activeSession: {
  id: string;
  title: string;
  mode: 'general' | 'coding' | 'meeting' | 'planning' | 'research' | 'personal';
  goal: string;
  startedAt: string;
  updatedAt: string;
  pinnedNoteIds: string[];
  linkedTaskIds: string[];
  summary?: string | null;
}
```

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
│  ├─ memory.py
│  └─ memory_state.py
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
├─ GET /health
└─ GET /api/status

Chat
├─ POST /api/chat
├─ POST /api/chat/stream
└─ POST /api/reset

Command interpreter
└─ POST /api/command/interpret

Search
└─ POST /api/search

Calendar
├─ GET /api/calendar/status
├─ POST /api/calendar/auth/start
├─ GET /api/calendar/auth/callback
├─ POST /api/calendar/auth/reset
├─ GET /api/calendar/events
├─ POST /api/calendar/events
├─ PATCH /api/calendar/events/{event_id}
└─ DELETE /api/calendar/events/{event_id}

Memory initialization
└─ GET /api/memory/initialization

Memory context
├─ GET /api/memory/status
├─ GET /api/memory/context
├─ PUT /api/memory/context
├─ GET /api/memory/export
├─ POST /api/memory/import
└─ POST /api/memory/clear

Active session
├─ GET /api/memory/session
├─ PUT /api/memory/session
├─ PATCH /api/memory/session
└─ DELETE /api/memory/session

Tasks
├─ GET /api/memory/tasks
├─ PUT /api/memory/tasks
├─ POST /api/memory/tasks
├─ PATCH /api/memory/tasks/{task_id}
├─ DELETE /api/memory/tasks/{task_id}
└─ POST /api/memory/tasks/clear-completed

Notes
├─ GET /api/memory/notes
├─ PUT /api/memory/notes
├─ POST /api/memory/notes
├─ DELETE /api/memory/notes/{note_id}
└─ POST /api/memory/notes/clear

Recent actions
├─ GET /api/memory/actions
├─ PUT /api/memory/actions
├─ POST /api/memory/actions
├─ DELETE /api/memory/actions/{action_id}
└─ POST /api/memory/actions/clear
```

## Memory model

The backend memory store keeps four main categories:

```text
backend/data/qmeet_memory.json
├─ tasks
├─ notes
├─ recentActions
└─ activeSession
```

The frontend treats backend memory as primary and browser localStorage/sessionStorage as fallback. This lets the Raspberry Pi frontend and laptop frontend share the same backend memory when pointed at the same FastAPI server.

Important memory notes:

```text
- memory initialization status prevents stale browser fallback from overwriting an intentionally empty backend
- JSON writes use a temp-file/replace flow
- backend memory operations are guarded by an in-process lock
- title-only task updates preserve completedAt state
- reset tasks clears activeSession.linkedTaskIds
- reset notes clears activeSession.pinnedNoteIds
```

## Streaming chat model

The frontend chat stream parser handles server-sent events from `/api/chat/stream`.

Current behavior:

```text
- normalizes VITE_QMEET_API_URL
- supports LF and CRLF event boundaries
- supports multi-line data fields
- treats done/error as terminal events
- reports stream-close-before-done as an explicit error
- cancellation uses AbortController
```

When an active focus exists, the chat stream hook adds a neutral context block so prompts like `how should I accomplish my focus` can resolve references to the active focus without mutating focus state.

## Calendar hardening

Calendar delete/edit flows refresh Google Calendar directly when connected so cold-start state does not block confirmed actions. The confirmed delete flow resolves its target from fresh calendar data instead of relying only on a possibly stale React state commit.

## Deployment notes

The app is still a prototype. Likely next improvements:

```text
├─ Phase 13 proactive focus suggestions
├─ camera/video as a future context input
├─ environment validation on backend startup
├─ production CORS tightening
├─ more robust memory storage than local JSON
├─ Pi startup service hardening
├─ frontend error boundary
├─ automated endpoint tests
└─ calendar-aware chat context
```
