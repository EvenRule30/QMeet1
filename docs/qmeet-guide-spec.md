# QMeet Guide Spec — Phase 17B v3

Phase 17B adds a friendly, bite-sized guide layer for people who do not know QMeet's exact commands yet.

## Goals

- Keep `what can you do` short and useful.
- Let users ask topic-specific questions like `help with focus` or `what is focus`.
- Route common onboarding questions into tool-aware answers instead of generic ChatGPT replies.
- Steer users toward real QMeet panels and commands.
- Answer simple UI follow-ups such as `what was that menu`, `how do I open it again`, and `can I click on these`.

## Guide topics

- Overview
- Context-sensitive next actions
- Current screen / panel help
- Focus
- Memory
- Tasks
- Notes
- Calendar
- Meetings
- Visual / camera context
- Search
- Voice
- UI
- Recaps

## Important command behavior

`what is focus` explains the feature.

`what is my focus` still reads the active focus session.

`show focus menu`, `open focus menu`, and `focus controls` open the Memory panel, because the Current Focus card and focus actions live there.

`what can I do now with it` returns context-aware suggestions. If an active focus exists, QMeet suggests commands such as:

- `set my goal to ...`
- `turn this focus into tasks`
- `save this focus as a note`
- `what should I do next`
- `open memory`

`can I click on any one of these` gives screen-aware UI guidance when QMeet can infer the current panel from the DOM.

## UI context detection

The guide infers the currently visible panel from the browser DOM instead of adding new global app state. It checks for recognizable text or elements for:

- Menu
- Memory
- Notes
- Calendar
- Search
- Settings
- Status
- Camera
- Chat

This is intentionally lightweight. If no panel is detected, QMeet gives a safe generic answer and points users to `open menu` or `open memory`.

## Backend routing

The backend command router now catches the same common guide/follow-up phrases before the general interpreter. It also maps focus-menu wording to `open memory` so fuzzy routing does not mislead users with `open menu`.

## Regression prompts

```text
what are you
what are you able to do
what is focus
help with focus
I'm working on a Java program for my class
what can I do now with it?
what was that menu that appeared before when the focus session started?
how do I open it again?
show focus menu
open menu
can I click on any one of these
what is my focus
```

Expected results:

- Feature explanation prompts are short and command-oriented.
- `what is focus` teaches the feature.
- `what is my focus` reads the actual active focus.
- `show focus menu` opens Memory.
- UI follow-up questions do not fall through to generic ChatGPT when the local guide can answer them.
