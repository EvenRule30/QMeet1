# QMeet Development Guide

This document is for contributors changing QMeet behavior. The root `README.md` is the setup/run guide; `docs/architecture.md` describes runtime ownership and system boundaries.

This guide was refreshed against `main` on August 21, 2026. It intentionally avoids maintaining a long phase-by-phase feature history because those lists become stale quickly.

## Development principles

QMeet development should preserve these rules:

- model reasoning may interpret intent, choose a capability, and propose semantic arguments;
- deterministic code validates and executes state-changing operations;
- verified receipts are required before QMeet claims a mutation happened;
- canonical Focus state is the only runtime authority for Active Focus;
- general Memory must not regain ownership of canonical Focus;
- an active Focus is context, not automatic ownership of every user turn;
- prefer architectural ownership fixes over phrase-specific exceptions;
- new promoted behavior should normally include regression coverage.

Read `docs/architecture.md` before changing agent routing, Focus, task identity, Calendar targeting, or tool continuation behavior.

## Local setup

Use the root README for the complete setup. The short version is:

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Linux/macOS activation:

```bash
source .venv/bin/activate
```

### Frontend

From the repository root:

```bash
npm install
npm run dev -- --host 0.0.0.0
```

`.env.local` normally contains:

```env
VITE_QMEET_API_URL=http://localhost:8000
```

## Backend environment

The checked-in `backend/.env.example` is the best reference for current supported defaults.

Core values:

```env
LLM_PROVIDER=mock
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
OPENAI_MAX_OUTPUT_TOKENS=300
FRONTEND_ORIGIN=http://localhost:5173
```

Calendar values:

```env
GOOGLE_CALENDAR_ENABLED=false
GOOGLE_CALENDAR_CREDENTIALS_FILE=google_credentials.json
GOOGLE_CALENDAR_TOKEN_FILE=token_calendar_events.json
GOOGLE_CALENDAR_REDIRECT_URI=http://localhost:8000/api/calendar/auth/callback
GOOGLE_CALENDAR_ID=primary
GOOGLE_CALENDAR_TIMEZONE=local
GOOGLE_CALENDAR_WRITE_ENABLED=false
```

Current Focus routing defaults:

```env
QMEET_FOCUS_MODE=shadow
QMEET_FOCUS_RESPONSE_MODE=guarded
QMEET_FOCUS_RESPONSE_TIMEOUT_SECONDS=15
QMEET_FOCUS_ROUTE_MODE=guarded
QMEET_FOCUS_ROUTE_MIN_CONFIDENCE=0.9
QMEET_FOCUS_NATIVE_READ_MODE=guarded
QMEET_FOCUS_NATIVE_WRITE_MODE=guarded
```

Do not casually change those Focus flags to force a test to pass. They are part of the guarded migration architecture.

`QMEET_ENABLE_LEGACY_FOCUS_BOOTSTRAP=1` is an explicit migration/bootstrap escape hatch. It should not be enabled for normal runtime development because canonical Focus is the authoritative source.

## Useful runtime checks

With the backend running:

```powershell
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:8000/api/status
Invoke-RestMethod http://localhost:8000/api/calendar/status
Invoke-RestMethod http://localhost:8000/api/memory/status
Invoke-RestMethod http://localhost:8000/api/agent/shadow/status
Invoke-RestMethod http://localhost:8000/api/focus/state
```

The exact response shape of internal/status endpoints may evolve. Use these primarily to verify connectivity and state availability, not as stable public API contracts.

## Test strategy

### Full backend suite

From `backend/`:

```bash
python -m unittest discover -s tests -v
```

### Frontend production build

From the repository root:

```bash
npm run build
```

Run both before treating a broad routing/state change as complete.

### Targeted tests first

The backend test suite is intentionally regression-heavy. During development, run the smallest tests that cover the ownership seam you changed, then expand outward.

Examples:

```powershell
python -m unittest backend.tests.test_focus_proposal_acceptance_phase21i4 backend.tests.test_focus_proposal_readback_phase21i4a
```

For other work, use the matching files under `backend/tests/` for the affected capability. The current suite includes focused coverage for:

- canonical Focus lifecycle, context, tasks, summaries, and routing;
- agent ownership/promotion for tasks, notes, Search, Calendar, and device/UI;
- absolute/range Calendar interpretation and mutation safety;
- composite planning/execution dependencies and result binding;
- tool-continuation grounding and stale-context isolation;
- UI contract regressions for Calendar, Settings, Status, and Memory panels.

Do not remove an older regression simply because a new routing layer makes its original implementation path obsolete. Update the assertion to preserve the behavioral/safety contract where appropriate.

## Manual smoke tests

Automated tests are necessary, but several QMeet behaviors are best checked as conversation sequences because ownership can depend on what happened immediately before the turn.

### General ownership

```text
hello
show my tasks
open settings
search for Framework Laptop reviews
```

An active Focus should not cause unrelated requests to be answered as Focus mutations.

### Focus lifecycle

```text
start a focus to plan a vacation
what is my focus
end focus anyway
resume my last focus
what is my focus
```

After a verified end, stale Memory/context should not resurrect the ended Focus.

### Canonical Focus readout

When the Focus has a next action:

```text
what is my focus
```

The visible readout should include the canonical next step. If the frontend compatibility projection omits it, check `GET /api/focus/state` before changing Focus storage.

### Focus proposal expiration

A useful regression sequence is:

```text
what should I do today?
show my tasks
okay lets do it
what is my focus
```

Expected behavior:

- Daily Brief may suggest a concrete first step for an active Focus that has no next action.
- `show my tasks` is an unrelated next turn and expires the proposal.
- the later `okay lets do it` is ordinary conversation, not an unspecified Focus mutation;
- canonical Focus state remains unchanged.

For direct acceptance, test the immediate sequence instead:

```text
what should I do today?
okay lets do it
what is my focus
```

If the proposal was fresh and canonically valid, the next step should be persisted and read back from canonical Focus state.

### Task identity safety

Use examples where the spoken reference is not an exact task title:

```text
I finished the invoice
I finished the presentation outline
```

A completion must resolve against authoritative open tasks. Zero matches should not mutate anything; multiple matches should not silently choose one.

### Calendar grounding

Exercise both semantic interpretation and explicit naming:

```text
create a meeting tomorrow at 3 PM
create an event tomorrow at 3 PM called Project Meeting
what is on my calendar Friday
```

Explicit `called` / `named` / `titled` content should outrank a conflicting model-proposed Calendar title.

## Current development checkpoint

As of August 21, 2026:

- the Phase 21I4/I4A Focus next-step proposal flow is live-verified;
- canonical `what is my focus` readback includes `nextAction`;
- an unrelated next turn expires a pending Focus proposal;
- a later natural acknowledgement without a fresh proposal stays conversational and does not mutate Focus;
- current `main` also includes the subsequent Phase 22 UI/continuation/Calendar grounding work.

### Known next Focus proposal seam

`backend/app/focus_proposal.py` currently keeps one process-global `_PENDING_PROPOSAL`.

The proposal itself is deliberately ephemeral and one-turn, and acceptance re-verifies canonical Focus before writing. That safety behavior should remain.

The next architectural improvement is to scope pending proposals to the conversation/session that received them so independent QMeet conversations cannot overwrite or expire each other's ephemeral proposal state.

Do not solve this by putting the proposal into general Memory. It should remain short-lived conversational state with canonical verification at execution time.

## Unified-agent development workflow

The current agent code is a staged promotion system, not a license for arbitrary direct tool execution.

Important files:

```text
backend/app/qmeet_agent_shadow.py
backend/app/qmeet_agent_composite.py
backend/app/qmeet_capabilities.py
backend/app/routers/agent_shadow.py
backend/app/tool_continuation.py
backend/app/qmeet_device_ui_ownership.py
backend/app/qmeet_device_ui_promotion.py
```

### When promoting a new single-intent behavior

Use this sequence:

1. Define the semantic ownership/action contract.
2. Let the agent propose only the arguments it can safely infer from user language.
3. Apply a deterministic ownership floor if a known safety/identity boundary needs protection.
4. Reuse the existing deterministic execution handler rather than creating a second implementation.
5. Resolve canonical identity at execution time.
6. Preserve confirmation behavior for mutations.
7. Generate the tool receipt from the verified result.
8. Ground the continuation in the current receipt/context.
9. Add regressions for correct ownership, ambiguity, stale state, and failure behavior.

### When promoting composite behavior

`qmeet_agent_composite.py` is intentionally observational at the planning stage.

A composite plan may order promoted atomic actions and express verified-output dependencies, but it must not:

- claim execution happened;
- invent canonical IDs;
- skip a capability's deterministic validation;
- create extra helpful steps the user did not request;
- weaken confirmation requirements.

Treat each step as a normal canonical action with its own execution contract.

## Focus development rules

Focus has stricter ownership requirements than ordinary Memory features.

### Canonical source

Use:

```text
backend/app/focus/
backend/data/qmeet_focus.json
GET /api/focus/state
```

as the Focus authority.

Do not use `memory.activeSession` or a frontend Focus projection to decide whether a Focus exists when canonical state is available.

### Verified writes

Focus lifecycle and durable context changes should use the verified native Focus execution paths. A model classification, legacy command match, or UI projection is not a write receipt.

### Read-after-write verification

For important Focus writes, prefer the established pattern:

```text
validate expected Focus identity/state
        |
        v
append verified canonical event(s)
        |
        v
read canonical Focus again
        |
        v
only then report the resulting state
```

This is especially important for lifecycle changes, linked task progress, and proposed next actions.

## Memory development rules

General Memory owns tasks, notes, recent actions, visual observations, and related compatibility data.

Do not add broad reset behavior that implicitly clears canonical Focus. The current Memory panel deliberately keeps scoped maintenance instead of treating all state as one document the UI can own.

Global task reads should remain global even if a Focus is active. Focus-linked task reads are a separate Focus-owned request when the user explicitly asks about the current Focus tasks.

## Tool continuation rules

The visible assistant message after a tool action must be based on the newest verified receipt, not stale conversation history.

Current isolation rules already protect global tasks, Focus, Search, and Calendar from several stale-history failure modes.

When adding a new promoted action, ask:

- What is the authoritative receipt?
- What older conversation state could contradict it?
- Does the continuation need the whole chat history, or only the original turn plus verified context?
- Could a stale tool card make QMeet claim that deleted/ended/changed state still exists?

Prefer the smallest context that preserves natural conversation while keeping the latest verified action authoritative.

## Calendar development rules

Calendar interpretation and Calendar execution are separate responsibilities.

The agent/interpreter may identify:

- requested operation;
- natural date/range;
- semantic event title/criteria;
- user-provided time.

Deterministic Calendar code must still:

- normalize/validate the request;
- resolve real event identity;
- reject zero/multiple ambiguous targets when appropriate;
- preserve explicit user-grounded title text;
- require the established confirmation/write gate;
- return the actual Calendar result.

Do not let a model-proposed event ID or fabricated title become authoritative execution data.

## Debugging routing problems

When QMeet does the wrong thing, identify which layer first diverged:

```text
1. user text
2. exact/local compatibility parse
3. agent ownership decision
4. deterministic ownership floor
5. capability argument validation
6. canonical target resolution
7. confirmation state
8. execution result
9. tool receipt
10. continuation response
```

Fix the earliest incorrect layer that can enforce the rule generally.

For example, if the agent classifies `okay lets do it` as Focus after the proposal expired, do not add a second phrase handler in the Focus executor. The ownership layer should recognize that without a fresh proposal the phrase is conversational.

## Repository areas to inspect

```text
src/app/App.tsx
src/app/api.ts
src/app/commands.ts
src/app/commandHandlers/
src/app/lib/
src/app/hooks/
src/app/components/
src/app/panels/

backend/app/main.py
backend/app/routers/
backend/app/qmeet_agent_shadow.py
backend/app/qmeet_agent_composite.py
backend/app/tool_continuation.py
backend/app/focus/
backend/app/memory_store.py
backend/app/calendar_service.py
backend/app/calendar_*_service.py
backend/tests/
```

## Data and secrets

Do not commit local credentials, tokens, or user state:

```text
.env.local
backend/.env
backend/google_credentials.json
backend/token_calendar_readonly.json
backend/token_calendar_events.json
backend/calendar_auth_state.json
backend/data/qmeet_memory.json
backend/data/qmeet_focus.json
```

Avoid committing personal camera/upload images unless they are intentional fixtures.

## Documentation maintenance

When architecture changes:

- keep the root README focused on installing/running/testing QMeet;
- update `docs/architecture.md` for ownership/state-flow changes;
- update this file for development workflow, test strategy, or current known seams;
- mark old phase-specific documents as historical instead of silently treating them as current architecture;
- prefer a dated current checkpoint over a permanent phase-history list.
