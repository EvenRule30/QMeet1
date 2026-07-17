# QMeet Architecture Snapshot

This document describes the current QMeet architecture after Phase 14H visual-context and camera-snapshot work. QMeet is still a prototype: the frontend owns the tablet/orb experience and the backend owns LLM calls, search, Google Calendar integration, fuzzy command routing, backend-local persistent memory, and snapshot analysis.

## High-level architecture

```text
User
├─ taps/types/speaks into React UI
│
Frontend
├─ Orb and chat interface
├─ local exact command parser
├─ fuzzy command interpreter client
├─ panels for notes, memory, calendar, search, settings, status, menu
├─ camera capture overlay
├─ hooks for backend status, memory, search, calendar, speech, chat streaming
├─ active focus/session UI and recent focus history
├─ visualContext UI and saved visual observations
├─ focus nudges and clickable focus actions
├─ command/result toast system
└─ typed API client for FastAPI
│
Backend
├─ FastAPI app
├─ feature routers
├─ OpenAI chat/search/command interpreter service
├─ OpenAI vision snapshot analysis route
├─ Google Calendar service
└─ local JSON memory store
│
External services
├─ OpenAI API
└─ Google Calendar API
```

## Frontend responsibilities

The frontend owns the tablet user experience. It handles visual state, orb state, panel state, camera preview/capture, speech recognition, speech synthesis, streaming response display, local command execution, confirmation gates, workflow memory controls, visual context controls, and fallback browser state.

```text
src/app/
├─ App.tsx
│  └─ top-level orchestration and remaining command flow
├─ api.ts
│  └─ typed client for FastAPI endpoints, snapshot analysis, and chat SSE parsing
├─ commands.ts
│  └─ exact local command parser
├─ types.ts
│  └─ shared frontend request/response/UI types
├─ camera/
│  └─ CameraCaptureOverlay.tsx
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
├─ syncs tasks, notes, recent actions, activeSession, recentFocusSessions, and visualContext
├─ keeps localStorage fallback active
├─ prevents stale fallback state from overwriting initialized backend memory
├─ preserves focus history and visualContext through debounced full-context saves
├─ handles memory import/export/reset controls
├─ exposes task/note/focus/history/visual actions
└─ mirrors active focus and visual context state for immediate UI readback

useSearchController
├─ owns search query/result/loading/error state
└─ runs and clears web searches

useCalendarController
├─ owns local calendar state
├─ owns Google Calendar state/status/error/loading
├─ handles Google auth start/reset
├─ reads Google Calendar events
├─ creates/edits/deletes calendar events
└─ refreshes connected Google Calendar state before cold-start edit/delete target resolution

useSpeechOutput
├─ owns voice output enabled state
├─ owns speech rate state
├─ persists voice settings
└─ speaks/stops assistant text

useChatStreamController
├─ owns chat messages
├─ owns streaming abort state
├─ sends normal streaming chat
├─ injects active focus context into chat when relevant
├─ injects last saved visual observation text into chat when relevant
├─ supports LLM-enhanced recap requests from memory commands
├─ cancels active responses
└─ surfaces backend/SSE errors through the chat UI

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
   ├─ deterministic pre-routing for focus/workflow/visual commands
   ├─ OpenAI or mock interpreter fallback
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

`App.tsx` still owns the main orchestration path:

```text
pending confirmation handling
cancel handling
exact local command parsing
destructive-command confirmation checks
feature-specific command handlers
panel commands
fuzzy backend command interpretation
normal chat fallback
```

For spoken prompts, the orb should enter a thinking/routing state as soon as the final transcript is submitted. It should not sit in Ready while backend command interpretation or chat stream startup is pending.

## Backend responsibilities

The backend owns LLM calls, web search, snapshot analysis, Google Calendar integration, persistent memory storage, and API routing.

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
│  ├─ memory_state.py
│  └─ visual.py
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

Visual analysis
└─ POST /api/visual/analyze-snapshot

Calendar
├─ GET    /api/calendar/status
├─ POST   /api/calendar/auth/start
├─ GET    /api/calendar/auth/callback
├─ POST   /api/calendar/auth/reset
├─ GET    /api/calendar/events
├─ POST   /api/calendar/events
├─ PATCH  /api/calendar/events/{event_id}
└─ DELETE /api/calendar/events/{event_id}

Memory state
└─ GET /api/memory/initialization

Memory context
├─ GET  /api/memory/status
├─ GET  /api/memory/context
├─ PUT  /api/memory/context
├─ GET  /api/memory/export
├─ POST /api/memory/import
└─ POST /api/memory/clear

Tasks
├─ GET    /api/memory/tasks
├─ PUT    /api/memory/tasks
├─ POST   /api/memory/tasks
├─ PATCH  /api/memory/tasks/{task_id}
├─ DELETE /api/memory/tasks/{task_id}
└─ POST   /api/memory/tasks/clear-completed

Notes
├─ GET    /api/memory/notes
├─ PUT    /api/memory/notes
├─ POST   /api/memory/notes
├─ DELETE /api/memory/notes/{note_id}
└─ POST   /api/memory/notes/clear

Recent actions
├─ GET    /api/memory/actions
├─ PUT    /api/memory/actions
├─ POST   /api/memory/actions
├─ DELETE /api/memory/actions/{action_id}
└─ POST   /api/memory/actions/clear

Active focus session
├─ GET    /api/memory/session
├─ PUT    /api/memory/session
├─ PATCH  /api/memory/session
└─ DELETE /api/memory/session

Recent focus sessions
├─ GET    /api/memory/sessions/recent
├─ PUT    /api/memory/sessions/recent
├─ POST   /api/memory/sessions/recent/clear
└─ DELETE /api/memory/sessions/recent/{session_id}

Visual context
├─ GET    /api/memory/visual
├─ PUT    /api/memory/visual
├─ PATCH  /api/memory/visual
├─ POST   /api/memory/visual/observations
├─ POST   /api/memory/visual/clear
└─ DELETE /api/memory/visual/observations/{observation_id}
```

## Memory model

The backend memory store keeps:

```text
backend/data/qmeet_memory.json
├─ version
├─ tasks
├─ notes
├─ recentActions
├─ activeSession
├─ recentFocusSessions
└─ visualContext
```

### ActiveSession

```ts
type ActiveSession = {
  id: string;
  title: string;
  mode: 'general' | 'coding' | 'meeting' | 'planning' | 'research' | 'personal';
  goal: string;
  startedAt: string;
  updatedAt: string;
  pinnedNoteIds: string[];
  linkedTaskIds: string[];
  summary?: string | null;
};
```

### RecentFocusSession

```ts
type RecentFocusSession = {
  id: string;
  title: string;
  mode: ActiveSession['mode'];
  goal: string;
  startedAt: string;
  endedAt: string;
  pinnedNoteIds: string[];
  linkedTaskIds: string[];
  summary?: string | null;
  summaryNoteId?: string | null;
};
```

### VisualContext

```ts
type VisualContext = {
  enabled: boolean;
  lastObservation: VisualObservation | null;
  recentObservations: VisualObservation[];
};

type VisualObservation = {
  id: string;
  source: 'camera' | 'screen' | 'manual';
  summary: string;
  capturedAt: string;
  confidence?: number | null;
  relatedFocusId?: string | null;
};
```

The frontend treats backend memory as primary and browser `localStorage` as fallback. This lets the Raspberry Pi frontend and laptop frontend share the same backend memory when pointed at the same FastAPI server.

Important memory rules:

```text
- Backend memory initialization state is checked separately from memory contents.
- Empty backend arrays can be intentional saved state.
- Browser fallback migration should only happen when backend memory has not been initialized.
- Backend writes should be atomic and locked within the FastAPI process.
- Partial task PATCH operations should preserve omitted fields.
- Clearing activeSession should archive it into recentFocusSessions when appropriate.
- Context saves that omit recentFocusSessions should preserve backend history.
- Context saves that omit visualContext should preserve backend visual context.
- Camera images are not stored in qmeet_memory.json; only text observations are stored.
```

## Active Context / Focus Session model

The active context layer is the current bridge between simple memory and perception-aware assistance.

```text
Active Focus
├─ mode
├─ title
├─ goal
├─ linked tasks
├─ pinned summary notes
├─ recent actions
└─ visual observations
```

Current implemented behavior:

```text
- focus can be started, updated, read, ended, and ended with summary
- focus appears in the top status bar and Memory panel
- focus can be turned into linked memory tasks
- focus can be summarized and saved as a note
- ending focus can guard against losing unsaved progress
- ended focus sessions archive into recentFocusSessions
- recent focus sessions can be recalled, listed, removed, cleared, or resumed
- chat receives neutral active focus context when relevant
- enhanced recap can send memory/focus context into the normal chat stream
- visual observations can link to the active focus through relatedFocusId
```

## Focus nudges and actions

The Memory panel includes focus nudges and common focus actions.

```text
No active focus
└─ suggest starting a focus

Active focus without goal
└─ suggest setting a goal

Active focus with goal but no linked tasks
└─ suggest turning focus into tasks

Active focus with linked tasks
└─ suggest next open linked task

Active focus with no saved note after time/progress
└─ suggest saving a progress note
```

Common focus actions are available directly when a focus exists:

```text
Create tasks
Save note
End with summary
```

## Visual context model

Visual context is QMeet's first perception-aware memory layer. It currently supports manual observations and one-shot camera snapshot observations.

```text
Manual observation
└─ user says: note visually that the tablet is on the desk
   └─ QMeet creates VisualObservation(source='manual')

Camera observation
└─ user opens camera, takes snapshot, clicks Analyze Snapshot
   ├─ browser sends one image to backend
   ├─ backend sends image to OpenAI vision
   ├─ backend returns text summary
   └─ frontend saves VisualObservation(source='camera')
```

Current behavior:

```text
- Memory panel shows Visual Context.
- Last visual observation is included in normal chat context.
- Explicit visual commands can read, list, summarize, delete, or clear observations.
- The camera overlay has local preview, snapshot, and analysis controls.
- Raw images are not persisted by QMeet.
```

Privacy/storage boundary:

```text
- Camera preview is browser-local.
- Snapshot is in browser memory only until closed/cleared/analyzed.
- Analyze Snapshot sends the image to the backend, then OpenAI.
- QMeet stores only the returned text observation.
- OpenAI receives the image when the OpenAI vision path is used.
```

## Chat streaming model

Normal chat uses `/api/chat/stream` with server-sent events.

Expected event types:

```text
start
chunk
done
error
```

The frontend SSE parser should tolerate:

```text
- LF and CRLF line endings
- multiple data: lines
- final buffered events without a trailing blank line
- explicit terminal done/error events
```

If a stream closes before `done` or `error`, the frontend should surface a clear stream-closed error and reset active response state.

Focus-aware and visual-aware chat context is neutral. QMeet passes active focus and last saved visual observation as user-provided context, not as a custom safety filter or policy layer. Normal assistant safety still applies at the model layer.

## Recap model

Phase 13F has two recap paths:

```text
Local recap
├─ deterministic memory summary
├─ active focus
├─ recent ended focus sessions
├─ tasks
├─ notes
└─ recent actions

Enhanced recap
├─ compact memory snapshot
├─ sent through the normal chat stream
├─ asks model for concise recap
├─ asks what changed
├─ lists open loops
└─ suggests next action
```

A future recap can include visual observations as another signal.

## Camera/snapshot analysis model

Phase 14E/F use a browser-first, one-shot snapshot model.

```text
Browser camera overlay
├─ getUserMedia preview
├─ one-shot snapshot to canvas/blob
├─ no image persistence
└─ Analyze Snapshot button

Backend visual route
├─ POST /api/visual/analyze-snapshot
├─ validates image/jpeg, image/png, image/webp
├─ enforces QMEET_MAX_SNAPSHOT_BYTES
├─ sends image to OpenAI vision when configured
├─ returns summary/model/contentType/bytes/confidence
└─ does not store the raw image

Frontend save path
├─ receives summary
├─ creates camera VisualObservation
├─ links relatedFocusId when activeSession exists
├─ updates visualContext immediately
└─ Memory panel and chat context see the observation
```

## Google Calendar model

QMeet supports both local fallback calendar events and connected Google Calendar events. Calendar writes are guarded by confirmations where appropriate, especially delete/edit operations. For connected Google Calendar, confirmed cold-start edit/delete flows should refresh Google Calendar and resolve the target from the fresh result instead of relying only on React state that may not have committed yet.

## Deployment notes

The app is still a prototype. Likely future deployment improvements:

```text
├─ environment validation on backend startup
├─ production CORS tightening
├─ more robust memory storage than local JSON
├─ Pi startup service hardening
├─ frontend error boundary
├─ automated endpoint tests
├─ calendar-aware chat context
├─ richer active context/event timeline
├─ visual observations in recaps
├─ optional snapshot resizing/compression
└─ optional continuous or interval visual awareness with explicit opt-in
```
