# QMeet Architecture Snapshot

This document describes the current QMeet architecture after Phase 15C visual-focus and UI polish work. QMeet is still a prototype: the frontend owns the tablet/orb experience and the backend owns LLM calls, search, Google Calendar integration, fuzzy command routing, visual analysis, and backend-local persistent memory.

## High-level architecture

```text
User
├─ taps/types/speaks into React UI
│
Frontend
├─ Orb and chat interface
├─ discreet chat-log toggle
├─ local exact command parser
├─ fuzzy command interpreter client
├─ panels for notes, memory, calendar, search, settings, status, menu
├─ camera capture/upload overlay
├─ hooks for backend status, memory, search, calendar, speech, chat streaming
├─ active focus/session UI and recent focus history
├─ visual context UI and visual-focus linking
├─ focus nudges and clickable focus actions
├─ command/result toast system
└─ typed API client for FastAPI
│
Backend
├─ FastAPI app
├─ feature routers
├─ OpenAI chat/search/command interpreter service
├─ OpenAI vision snapshot analysis endpoint
├─ Google Calendar service
└─ local JSON memory store
│
External services
├─ OpenAI API
└─ Google Calendar API
```

## Frontend responsibilities

The frontend owns the tablet user experience. It handles visual state, orb state, panel state, camera overlay state, speech recognition, speech synthesis, streaming response display, local command execution, confirmation gates, workflow memory controls, visual-context controls, and fallback browser state.

```text
src/app/
├─ App.tsx
│  └─ top-level orchestration and remaining command flow
├─ api.ts
│  └─ typed client for FastAPI endpoints, chat SSE parsing, visual analysis upload
├─ commands.ts
│  └─ exact local command parser
├─ types.ts
│  └─ shared frontend request/response/UI types
├─ camera/
│  └─ CameraCaptureOverlay.tsx
├─ components/
│  ├─ ChatLogToggle.tsx
│  └─ reusable UI components
├─ hooks/
│  └─ feature state controllers
├─ commandHandlers/
│  └─ command execution branches grouped by feature
├─ lib/
│  └─ pure helper utilities
└─ panels/
   └─ overlay wrappers for panel UI
```

## Important frontend hooks and components

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
├─ handles memory import/export/reset controls
├─ exposes task/note/focus/history/visual actions
└─ mirrors active focus and visual state for immediate UI readback

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
├─ injects latest visual observation context when available
├─ supports LLM-enhanced recap requests from memory commands
├─ cancels active responses
└─ surfaces backend/SSE errors through the chat UI

useSpeechRecognitionController
├─ starts browser speech recognition
├─ manages listening transcript preview
├─ handles silence timeout
├─ handles microphone/browser errors
└─ sends final transcript to App command routing

CameraCaptureOverlay
├─ browser getUserMedia preview
├─ one-shot webcam snapshots
├─ image upload analysis path
├─ backend snapshot/image analysis call
├─ text-only visual observation save
├─ Reset preview workaround for blurry webcam preview
└─ compact upload metadata/no-preview fallback

ChatLogToggle
├─ discreet lower-left chat-log opener
├─ opens chat/prompt without starting voice input
├─ uses smooth chat/orb layout transition
└─ closes idle peek with Escape
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

The backend owns LLM calls, web search, Google Calendar integration, snapshot/image analysis, persistent memory storage, and API routing.

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

Visual analysis
└─ POST /api/visual/analyze-snapshot

Calendar
├─ GET /api/calendar/status
├─ POST /api/calendar/auth/start
├─ GET /api/calendar/auth/callback
├─ POST /api/calendar/auth/reset
├─ GET /api/calendar/events
├─ POST /api/calendar/events
├─ PATCH /api/calendar/events/{event_id}
└─ DELETE /api/calendar/events/{event_id}

Memory state
└─ GET /api/memory/initialization

Memory context
├─ GET /api/memory/status
├─ GET /api/memory/context
├─ PUT /api/memory/context
├─ GET /api/memory/export
├─ POST /api/memory/import
└─ POST /api/memory/clear

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

Active focus session
├─ GET /api/memory/session
├─ PUT /api/memory/session
├─ PATCH /api/memory/session
└─ DELETE /api/memory/session

Recent focus sessions
├─ GET /api/memory/sessions/recent
├─ PUT /api/memory/sessions/recent
├─ POST /api/memory/sessions/recent/clear
└─ DELETE /api/memory/sessions/recent/{session_id}

Visual context
├─ GET /api/memory/visual
├─ PUT /api/memory/visual
├─ PATCH /api/memory/visual
├─ POST /api/memory/visual/observations
├─ POST /api/memory/visual/clear
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
- QMeet stores visual observations as text; raw images are not persisted by default.
```

## Active Context / Focus Session model

The active context layer is the bridge between simple memory, workflow memory, and perception-aware assistance.

```text
Active Focus
├─ mode
├─ title
├─ goal
├─ linked tasks
├─ pinned summary notes
├─ linked visual observations
├─ recent actions
└─ eventual richer perception observations
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
- enhanced recap can send memory/focus/visual context into the normal chat stream
- latest visual observation can be linked to the active focus
- focus summaries include linked visual observations
```

## Visual context model

Phase 14 and Phase 15 added the first visual loop:

```text
manual visual note
or camera snapshot
or uploaded image
   -> backend/model description
   -> VisualObservation text record
   -> Memory panel / chat context / focus link
```

Sources:

```text
manual  user-provided visual note
camera  webcam snapshot analyzed through backend/OpenAI
screen  reserved for future screen/context observation support
```

Current camera/upload behavior:

```text
- camera preview uses browser getUserMedia
- Snapshot captures one frame in memory
- Analyze Snapshot sends image bytes to /api/visual/analyze-snapshot
- backend uses OpenAI vision when configured
- QMeet saves only returned text description
- uploaded images use same analysis route
- uploaded image UI intentionally avoids embedded previews because preview rendering was inconsistent
```

Known caveats:

```text
- Webcam preview can blur on some browser/device combinations.
- Reset preview performs a close/reopen-style lifecycle inside the overlay and is the current workaround.
- A blurry preview does not necessarily mean the actual snapshot or OpenAI analysis is blurry.
- Uploaded images are analyzed from their original file blob, not from any embedded preview rendering.
- Use Open original for inspecting an uploaded file.
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
Link visual
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

Focus-aware and visual-aware chat context is neutral: QMeet passes the active focus and last saved visual observation as user-provided context, not as a custom safety filter or policy layer. Normal assistant safety still applies at the model layer.

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
├─ visual context when available
├─ sent through the normal chat stream
├─ asks model for concise recap
├─ asks what changed
├─ lists open loops
└─ suggests next action
```

## Camera/upload privacy model

```text
QMeet local app
├─ does not store raw webcam snapshots in memory
├─ does not store uploaded image files in memory
├─ stores only generated text observations
└─ links observations to focus through relatedFocusId when requested

Backend
├─ receives image bytes for /api/visual/analyze-snapshot
├─ validates content type and size
├─ sends image to OpenAI vision when configured
└─ returns text summary without saving raw image
```

OpenAI receives images for analysis when OpenAI vision is enabled. API data is not used for model training by default, but may be temporarily retained under OpenAI's API data-retention policy depending on account settings.

## Google Calendar model

QMeet supports both local fallback calendar events and connected Google Calendar events. Calendar writes are guarded by confirmations where appropriate, especially delete/edit operations.

For connected Google Calendar, confirmed cold-start edit/delete flows should refresh Google Calendar and resolve the target from the fresh result instead of relying only on React state that may not have committed yet.

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
├─ optional screen observation model
└─ optional continuous/periodic camera awareness with explicit user controls
```
