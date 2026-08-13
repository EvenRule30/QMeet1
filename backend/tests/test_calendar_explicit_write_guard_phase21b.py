from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CalendarExplicitWriteGuardPhase21BTests(unittest.TestCase):
    def test_explicit_calendar_write_guard_runs_before_agent_first_ownership(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        guard_index = source.index("resolveExplicitCalendarWriteIntentBeforeAgent({")
        agent_index = source.index("await resolvePromotedSingleIntentDecision({")
        self.assertLess(guard_index, agent_index)
        self.assertIn("!explicitCalendarWriteIntent", source)

    def test_no_time_schedule_reenters_existing_parser_instead_of_agent_execution(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("^schedule\\s+(.+?)\\s+", source)
        self.assertIn("const canonicalFrontendCommand = `add event ${day} called ${title}`;", source)
        self.assertIn("const commandMatch = parseCommand(canonicalFrontendCommand);", source)
        self.assertIn("commandMatch.command !== 'add-calendar-event'", source)
        self.assertIn("expectedAction: 'add-calendar-event'", source)
        self.assertIn("It never executes a", source)
        self.assertIn("Calendar write itself.", source)

    def test_explicit_schedule_normalization_uses_existing_later_time_behavior(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("schedule <title> today|tomorrow", source)
        self.assertIn("Later-time behavior", source)
        self.assertNotIn("time: 'Later'", source)
        self.assertNotIn('time: "Later"', source)

    def test_underspecified_delete_is_guarded_without_synthesizing_a_delete_command(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        delete_index = source.index("return 'delete-calendar-event';")
        return_index = source.index("return {\n    expectedAction,", delete_index)
        self.assertLess(delete_index, return_index)
        self.assertIn("They deliberately do not create a CommandMatch", source)
        self.assertIn("delete tomorrow's meeting", source)

    def test_explicit_guard_action_is_used_by_existing_verified_write_handoff(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn(
            "explicitCalendarWriteIntent?.expectedAction ??\n      resolveDeferredCalendarWriteAction(promotedSingleIntent)",
            source,
        )
        self.assertIn("parseVerifiedCalendarWriteAction", source)
        self.assertIn(
            "interpretedCalendarWriteAction !== deferredCalendarWriteAction",
            source,
        )
        self.assertIn("Calendar write not safely resolved", source)
        self.assertIn("No calendar change was made.", source)

    def test_cross_capability_add_without_calendar_noun_is_not_claimed_by_explicit_guard(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "/^(?:add|create|make|put)\\b/i.test(writeText) &&\n    CALENDAR_TARGET_TERM.test(writeText)",
            source,
        )
        self.assertNotIn("practice time", source)
        self.assertNotIn("presentation", source)

    def test_schedule_noun_read_statements_are_not_treated_as_writes(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("SCHEDULE_AS_NOUN_OR_READ", source)
        self.assertIn("looks?", source)
        self.assertIn("appears?", source)
        self.assertIn("if (SCHEDULE_AS_NOUN_OR_READ.test(writeText)) return null;", source)

    def test_broad_schedule_planning_is_not_collapsed_into_one_calendar_event(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("BROAD_SCHEDULING_PLAN_TITLE", source)
        self.assertIn("(?:day|schedule|agenda|plans?)", source)
        self.assertIn("BROAD_SCHEDULING_PLAN_TITLE.test(title)", source)

    def test_polite_explicit_calendar_write_prefix_is_normalized_before_classification(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("(?:can|could|would|will)\\s+you\\s+(?:please\\s+)?", source)


if __name__ == "__main__":
    unittest.main()
