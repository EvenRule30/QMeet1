# QMeet Documentation

This directory contains current runtime/development documentation plus a small number of older design and phase-specific reference files.

Use this page to distinguish current source-of-truth documentation from historical context.

## Start here

### `../README.md`

Primary user/run guide.

Use it for:

- installing backend/frontend dependencies;
- environment setup;
- starting FastAPI and Vite;
- enabling OpenAI and Google Calendar;
- first-run smoke tests;
- basic troubleshooting;
- Raspberry Pi entry points.

The root README is intentionally not a complete feature or architecture catalog.

### `architecture.md`

Current runtime architecture.

Use it before changing:

- unified-agent ownership/routing;
- deterministic execution boundaries;
- canonical Focus state;
- task/Calendar target resolution;
- tool continuation grounding;
- Memory vs Focus ownership;
- composite planning/execution.

This is the primary architecture reference.

### `development.md`

Current contributor workflow.

Use it for:

- backend/frontend test commands;
- environment flags;
- manual conversation smoke tests;
- regression strategy;
- agent-promotion workflow;
- Focus/Memory/Calendar development guardrails;
- current known migration seams.

### `pi-kiosk.md`

Raspberry Pi Chromium kiosk setup.

Use it for:

- laptop-hosted vs Pi-hosted layouts;
- LAN configuration;
- `pi-kiosk-start.sh` options;
- microphone/camera profile persistence;
- kiosk autostart;
- display and connectivity troubleshooting.

### `pi-kiosk-autostart-example.desktop`

Example desktop autostart entry for the Pi.

The repository path and `QMEET_URL` are examples and must be changed to match the actual installation.

## Historical / reference documents

### `phase-14-camera-readiness.md`

Historical camera-readiness and compatibility notes from the Phase 14 implementation period.

Useful when investigating why the visual/camera pipeline was designed a certain way, but it is not the current overall architecture source of truth.

### `qmeet-guide-spec.md`

Design/reference material for the QMeet guide/UI concept.

Treat it as product/design context rather than a guarantee of current runtime behavior. When it conflicts with current code, tests, or `architecture.md`, the current implementation and canonical architecture win.

## Documentation ownership rules

When QMeet changes:

- update the root README only when install/run/first-use instructions change;
- update `architecture.md` when runtime ownership, canonical state, routing, or execution boundaries change;
- update `development.md` when contributor workflow, tests, flags, or active migration seams change;
- update `pi-kiosk.md` when the launcher or Pi deployment assumptions change;
- keep phase-specific investigation notes historical unless they are deliberately promoted into a current document.

Avoid adding a permanent feature/phase timeline to the root README. Git history and regression names already preserve implementation history; the docs should prioritize how QMeet works now.

## Current architectural orientation

QMeet is moving toward one conversational agent that can understand general chat and supported capabilities, while deterministic backend/frontend systems remain authoritative for real state changes.

The key invariant is:

```text
model reasoning -> semantic intent/plan
                     |
                     v
deterministic validation + canonical execution
                     |
                     v
verified receipt -> conversational continuation
```

Active Focus follows the same rule. It is useful context when relevant, but it is not universal ownership of every user turn, and its canonical backend state must outrank legacy Memory projections.
