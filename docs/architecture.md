# QMeet Architecture

This document describes the current runtime architecture of QMeet as audited against `main` on August 21, 2026. It replaces the older Phase 15-era architecture snapshot.

QMeet architectural direction: use model reasoning to understand intent and conversational context, while keeping deterministic feature code and canonical backend state authoritative for actions that read or change real application state.

## Core design rules

The most important rules are:

1. **Reasoning and execution are separate.** The model can classify a turn, choose a capability, propose arguments, and plan a response. It does not prove that a state change happened.
2. **Deterministic systems remain authoritative.** Calendar, tasks, Focus, device/UI, and other promoted capabilities validate and execute through their existing deterministic paths.
3. **Verified receipts outrank model assumptions.** After an action runs, the visible continuation is grounded in the actual execution result rather than a predicted result.
4. **Active Focus is context, not universal ownership.** An active Focus may help answer a related request, but unrelated Calendar, Search, task, Memory, device, or general-chat turns stay with their own capability.
5. **Canonical Focus state is authoritative.** Legacy Memory/session projections may remain for compatibility, but they cannot decide whether a Focus exists or mutate Focus independently.
6. **State-changing behavior should fail closed.** Ambiguous targets, stale identity, failed verification, or unavailable canonical state should block or clarify rather than fabricate success.

These rules are more durable than individual phase names and should be preserved as the system moves toward a more unified QMeet agent.

## Runtime overview

```text
User
  |
  v
React / Vite tablet UI
  |- orb, chat, panels, voice, camera
  |- exact local command compatibility paths
  |- promoted agent-routing paths
  |- confirmation UX and feature handlers
  |
  v
FastAPI backend
  |
  +--> unified-agent semantic decision
  |      |- turn owner
  |      |- Focus relevance
  |      |- conversation / tool / clarify disposition
  |      `- proposed capability, action, and semantic arguments
  |
  +--> deterministic ownership floors and capability validation
  |
  +--> canonical feature execution
  |      |- Focus
  |      |- Calendar
  |      |- tasks / notes / Memory
  |      |- Search
  |      |- device/UI
  |      `- visual analysis
  |
  +--> verified result / receipt
  |
  `--> tool continuation or normal chat response

External services
  |- OpenAI API
  `- Google Calendar API
```

QMeet is in a staged unified-agent transition. Some compatibility command paths still exist, but many natural-language paths already use the unified agent to decide semantic ownership before deterministic execution.

## Frontend responsibilities

The frontend under `src/app/` owns the tablet experience and the client-side orchestration needed to present deterministic tool results naturally.

Important areas include:

```text
src/app/
|- App.tsx
|  `- top-level QMeet interaction and panel/orb orchestration
|- api.ts
|  `- typed FastAPI requests and streaming helpers
|- commands.ts
|  `- exact local command compatibility parser
|- commandHandlers/
|  `- deterministic feature execution adapters
|- hooks/
|  `- feature state and backend synchronization
|- lib/
|  `- shared routing/readout/helper utilities
|- components/
|  `- reusable UI and Calendar components
|- panels/
|  `- Memory, Search, Settings, Status, and other overlays
`- camera/
   `- browser camera/snapshot UI
```

The exact parser is still useful for stable local interactions and compatibility, but it is no longer the only semantic layer. Promoted natural requests can be owned by the agent and then passed into the existing handlers.

### Canonical Focus readout

`src/app/lib/canonicalFocusReadout.ts` reads `GET /api/focus/state` and formats the authoritative Focus state for the user. The `read-focus-session` behavior in `commandHandlers/memory.ts` attempts this canonical read before falling back to older display/read compatibility behavior.

That distinction matters because the frontend Memory projection may lag fields such as `nextAction`; it is not allowed to become the source of truth for Focus ownership.

## Backend entry point and middleware

`backend/app/main.py` creates the FastAPI application and installs canonical Focus compatibility before the middleware stack is imported.

The important startup rule is:

```text
canonical Focus read adapter
        |
        v
background work-context compatibility
        |
        v
Focus native read routing / Focus shadow middleware
        |
        v
feature routers
```

`install_canonical_work_context_source()` adapts the canonical Focus state into the older background-coaching read shape. This prevents stale `activeSession` data in general Memory from resurrecting a Focus that has already ended canonically.

The app registers routers for chat, unified-agent shadow/decision APIs, tool continuation, command compatibility, Search, Calendar, Memory, visual analysis, Focus, and Focus lifecycle operations.

`/api/chat/tool-continuation/stream` is intentionally a response-generation seam, not a new Focus turn. A successful tool action should not accidentally create a second mutation opportunity merely because QMeet is composing a conversational follow-up.

## Unified-agent decision layer

The current agent implementation lives primarily in:

```text
backend/app/qmeet_agent_shadow.py
backend/app/routers/agent_shadow.py
backend/app/qmeet_capabilities.py
```

The historical `shadow` name remains, but the endpoint now supplies semantics used by promoted runtime paths.

`POST /api/agent/shadow/decide` returns a structured decision containing concepts such as:

- `turnOwner`
- `focusRelevant`
- `disposition`
- proposed capability/action
- proposed semantic arguments
- response plan
- confidence/reason metadata

The model is instructed to decide turn ownership before deciding whether Focus matters.

Representative owners include:

```text
general_chat
calendar
search
memory
tasks
notes
focus
device_ui
visual
other
```

### Focus relevance is separate from ownership

A turn can be Calendar-owned and still use Focus as relevant context. For example, adding practice time for an active presentation Focus is still a Calendar operation if the user is asking to create a Calendar event.

Conversely, an unrelated request such as `show my tasks`, `open settings`, or a general knowledge question should not be pulled into Focus merely because a Focus is active.

A pending Focus coaching question is also advisory context, not a conversational lock.

## Deterministic ownership floors

The raw model decision is not automatically trusted. `backend/app/routers/agent_shadow.py` applies deterministic ownership floors after the model returns.

Current floors include areas such as:

- direct device/UI control
- Calendar absolute-date create
- Calendar edit/delete targeting
- Calendar range reads
- Daily Brief ownership
- one-turn Focus proposal acceptance

These floors exist to preserve known contracts when a model decision is too broad, too eager, or semantically unsafe.

This is an important architectural pattern: **agent reasoning can expand natural-language coverage without removing deterministic authority.**

## Single-intent execution flow

For a promoted single-intent tool request, the intended flow is:

```text
user turn
  |
  v
agent semantic decision
  |
  v
deterministic ownership repair / validation
  |
  v
existing canonical feature handler
  |
  v
zero / one / many target resolution where needed
  |
  v
confirmation gate for mutations where required
  |
  v
verified execution result
  |
  v
tool receipt
  |
  v
grounded conversational continuation
```

The agent may propose semantic lookup criteria, but deterministic code resolves authoritative object identity. A model-proposed task/event/Focus identifier must not be treated as canonical identity simply because the model supplied one.

## Composite-intent planning

`backend/app/qmeet_agent_composite.py` supports multi-capability planning for promoted atomic actions.

The planner is explicitly observational: it can describe ordered steps and dependencies, but it cannot execute tools, mutate state, confirm an action, or claim success.

Important composite rules include:

- do not split one semantic action into fake multiple steps;
- do not invent follow-up actions the user did not request;
- use only promoted canonical atomic actions;
- do not invent canonical IDs;
- resolve real identities later through deterministic feature code;
- use verified output bindings only when a later step truly depends on an earlier result.

Focus is deliberately more conservative in composite planning because it has additional canonical ownership and lifecycle semantics.

## Tool continuation and stale-context isolation

After a tool executes, `backend/app/tool_continuation.py` builds the context used for QMeet's visible follow-up response.

This layer is intentionally grounded in the current action. Recent work isolates several capability continuations from stale cross-capability history.

For example:

- global task continuations use the original user turn plus the verified task receipt/context;
- Focus-owned continuations use the original turn, current verified receipt/context, and the current canonical Focus snapshot when one remains active;
- Search and Calendar continuations similarly avoid letting older tool cards override the newest verified result.

This prevents errors such as an old `Saved task` receipt being repeated after the task was deleted, or an older Memory interaction reintroducing a Focus after a verified Focus end.

## Active Focus

Active Focus is the most state-sensitive subsystem in QMeet.

The canonical implementation is under:

```text
backend/app/focus/
```

The main runtime data file is:

```text
backend/data/qmeet_focus.json
```

or the path configured through `QMEET_FOCUS_FILE`.

### Canonical Focus model

Focus is event-backed. Verified operations append canonical Focus events, and current state is reduced from that event history.

The canonical lifecycle covers behaviors such as:

- start
- update title/objective/mode
- add structured context
- set or update next action
- link/create Focus tasks
- track linked-task progress
- save summaries
- end or complete
- resume prior Focus
- prepare from Calendar context

Important modules include:

```text
backend/app/focus/store.py
backend/app/focus/models.py
backend/app/focus/lifecycle.py
backend/app/focus/context.py
backend/app/focus/tasks.py
backend/app/focus/task_progress.py
backend/app/focus/task_lineage.py
backend/app/focus/summary.py
backend/app/focus/calendar_prep.py
backend/app/focus/planner.py
backend/app/focus/middleware.py
backend/app/focus/native_read_middleware.py
backend/app/focus/canonical_work_context_source.py
```

### Canonical Focus vs legacy Memory

Older QMeet versions stored an active session inside the general Memory document. That representation may still be projected for compatibility with older UI and coaching code, but the canonical Focus store is the only runtime authority for whether a Focus is active and what its authoritative state is.

Normal runtime should not enable legacy Focus bootstrap. `QMEET_ENABLE_LEGACY_FOCUS_BOOTSTRAP=1` is an explicit migration/bootstrap escape hatch, not a normal operating mode.

### Focus next-step proposals

Daily Brief can propose a concrete next step when the active canonical Focus does not already have one. A short immediate acknowledgement such as `okay lets do it` can accept that proposal only while it is fresh and still matches the same canonical Focus state.

The proposal is one-turn conversational context, not durable Memory. Any unrelated next turn expires it. Acceptance consumes the proposal and re-verifies canonical Focus identity/status/current next action before writing `NEXT_ACTION_SET`.

If no fresh proposal exists, the same natural acknowledgement is forced back to normal conversation rather than becoming an unspecified Focus mutation.

### Current proposal-isolation seam

As of this audit, `backend/app/focus_proposal.py` still stores the pending proposal in one process-global `_PENDING_PROPOSAL` protected by a lock. The acceptance behavior is canonical and fail-closed, but the ephemeral proposal itself is not yet scoped per conversation/session.

That means multi-conversation isolation is a known next architectural seam: one conversation should eventually be unable to overwrite or expire another conversation's pending proposal.

Do not work around this by persisting proposals into general Memory or by weakening canonical verification. The correct direction is conversation-scoped ephemeral ownership.

## General Memory, tasks, notes, and visual context

General Memory remains separate from canonical Focus.

Prototype-local general data lives in:

```text
backend/data/qmeet_memory.json
```

It contains non-Focus state such as:

- global tasks
- notes
- recent actions/history
- visual observations
- compatibility projections used by older UI seams

The Memory UI has intentionally moved away from broad reset behavior. General Memory cleanup must not imply ownership of canonical Focus state.

Global task reads are task-owned, not Focus-owned, unless the user specifically asks about tasks linked to the current Focus.

## Calendar

Google Calendar is a separate deterministic capability. Natural-language interpretation can determine the requested operation and semantic target, but Calendar state and target resolution remain authoritative in Calendar code.

The backend now has dedicated interpretation/service seams for relative and absolute dates, range reads, creates, edits, and deletes, including:

```text
backend/app/calendar_service.py
backend/app/calendar_read_date_interpreter.py
backend/app/calendar_range_service.py
backend/app/calendar_absolute_create_service.py
backend/app/calendar_absolute_update_service.py
```

Recent Calendar hardening also preserves explicit user naming. If the user says an event is `called`, `named`, or `titled` something, that explicit title is treated as user-grounded execution data and outranks a conflicting model-proposed title.

The Calendar panel can navigate arbitrary dates while preserving the existing relative today/tomorrow flows.

## Device/UI ownership

Direct requests such as opening a panel, navigating, or controlling voice belong to the device/UI capability rather than general chat or Focus.

Agent semantics can recognize these requests, but promoted device/UI execution remains bounded by the existing deterministic action vocabulary and frontend runtime controls.

This keeps model reasoning from turning arbitrary text into arbitrary UI execution.

## Search and external information

Requests that explicitly require current external evidence, reviews, verification, or web opinions should be Search-owned rather than answered from model memory.

Search execution remains a deterministic capability after agent classification. Search continuations are grounded in the current result rather than stale prior tool cards.

## State authority table

| State / behavior | Runtime authority | Compatibility / projection role |
| --- | --- | --- |
| Active Focus lifecycle | canonical Focus event store | legacy Memory session is read/display compatibility only |
| Focus next action | canonical Focus state/events | frontend readout formats canonical state |
| Global tasks | backend Memory/task store | Focus may link task IDs but does not own unrelated global task reads |
| Notes | backend Memory/note store | Focus summaries may create/link notes through verified flows |
| Calendar events | Google Calendar + deterministic Calendar services | agent supplies semantic intent, not authoritative event identity |
| Device/UI state | frontend deterministic controls | agent may choose a supported device/UI action |
| Search result | Search capability execution | agent decides when external evidence is required |
| Tool success | verified handler/service receipt | model continuation describes the receipt; it does not manufacture it |

## Important API surfaces

Representative current routes include:

```text
GET  /health
GET  /api/status
POST /api/chat/stream
POST /api/chat/tool-continuation/stream
GET  /api/agent/shadow/status
POST /api/agent/shadow/decide
POST /api/agent/shadow/plan
GET  /api/focus/state
GET  /api/calendar/status
GET  /api/memory/status
```

Feature routers expose additional operation-specific endpoints. Treat the router code and tests as authoritative if a route name changes.

## Current transition seams

The main architecture is intentionally transitional rather than fully collapsed into one agent loop.

Areas that still deserve careful treatment include:

1. **Conversation-scoped proposal ownership.** Pending Focus next-step proposals are still process-global ephemeral state.
2. **Compatibility command paths.** Exact frontend commands and older routing seams remain alongside promoted agent ownership.
3. **Legacy Focus projections.** They are still needed by some UI/background compatibility code and must stay subordinate to canonical Focus.
4. **Composite execution coverage.** Composite planning is constrained to promoted atomic actions and should expand only behind deterministic validation.
5. **Agent naming.** The `shadow` module/route names reflect the migration history even where decisions are now used by promoted runtime behavior.

These are migration seams, not invitations to bypass the safety boundaries above.

## Architectural regression principles

When changing QMeet, regression coverage should prove behavior at the ownership boundary, not just match phrases.

Examples:

- a global task request stays global even when a Focus is active;
- a Calendar request can use Focus context without becoming a Focus mutation;
- a model-proposed object target is re-resolved against authoritative state;
- a stale or ambiguous target cannot be reported as successfully changed;
- ending Focus prevents stale Memory from resurrecting it;
- a tool continuation cannot override the newest verified action with old conversation history;
- an expired Focus proposal acknowledgement remains ordinary conversation;
- canonical Focus reads expose fields such as `nextAction` even if a compatibility projection does not.

Prefer canonical ownership and deterministic verification over adding isolated phrase-specific exceptions.

## Where to start reading the code

For runtime behavior, a useful order is:

```text
src/app/App.tsx
src/app/api.ts
backend/app/main.py
backend/app/routers/agent_shadow.py
backend/app/qmeet_agent_shadow.py
backend/app/qmeet_agent_composite.py
backend/app/tool_continuation.py
backend/app/focus/
backend/app/memory_store.py
backend/app/calendar_service.py
backend/tests/
```

For setup and test commands, use `README.md` and `docs/development.md` rather than this architecture document.
