# QMeet Guide Spec

Phase 17B-v2 turns QMeet help into a small feature guide instead of one long paragraph.

## Goals

- Let new users ask normal questions like `what are you able to do?` or `can you make me a schedule?`.
- Return short, topic-specific answers with commands they can try immediately.
- Steer users toward real QMeet tools: focus, memory, notes, tasks, calendar, meetings, visual context, search, voice, UI, and recaps.
- Avoid stealing normal work prompts such as `help me complete my focus`.

## Guide topics

- Overview
- Focus
- Memory
- Tasks
- Notes
- Calendar / schedule
- Meetings
- Camera / visual context
- Search
- Voice
- UI
- Recaps

## New natural examples

These should route to bite-sized guide responses:

```text
what are you able to do
what can you help me with
how are you able to help
how are you able to do
can you make me a schedule
help with calendar
help with focus
examples for camera
```

## Natural prep examples

These should route to actual focus tools instead of generic chat:

```text
I have an appointment at 6:00 p.m. today I need to prepare for
you can start that focus preparation block
start the prep block
```

Expected result: QMeet creates a meeting-prep focus session rather than merely saying it will.

## Style

Guide answers should be short, practical, and example-driven. Prefer:

```text
I can do X. Try: "command one", "command two", or "command three".
```

over large paragraphs.
