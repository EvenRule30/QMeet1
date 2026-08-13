from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CalendarExplicitWriteGuardPhase21BTests(unittest.TestCase):
    def test_explicit_calendar_write_fallback_is_observed_before_agent_but_does_not_block_agent(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        fallback_index = source.index("resolveExplicitCalendarWriteIntentBeforeAgent({")
        agent_index = source.index("await resolvePromotedSingleIntentDecision({")
        self.assertLess(fallback_index, agent_index)

        promoted_assignment = source[
            source.index("const promotedSingleIntent =") : agent_index + 160
        ]
        self.assertNotIn("!explicitCalendarWriteIntent", promoted_assignment)
        self.assertIn(
            "promotedSingleIntent?.disposition === 'conversation' &&\n      !explicitCalendarWriteIntent",
            source,
        )

    def test_calendar_write_fallback_no_longer_synthesizes_commands_or_arguments(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("Deterministic ownership fallback only", source)
        self.assertIn("never synthesizes arguments", source)
        self.assertIn("expectedAction", source)
        self.assertNotIn("parseCommand", source)
        self.assertNotIn("canonicalFrontendCommand", source)
        self.assertNotIn("commandMatch:", source)
        self.assertNotIn("add event ${day} called ${title}", source)

    def test_explicit_schedule_without_time_is_calendar_owned_but_left_for_agent_create_proposal(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("/^schedule\\b/i.test(writeText)", source)
        self.assertIn("return 'add-calendar-event';", source)
        self.assertIn("BROAD_SCHEDULING_PLAN_TITLE", source)
        self.assertNotIn("time: 'Later'", source)
        self.assertNotIn('time: "Later"', source)

    def test_underspecified_delete_is_calendar_owned_without_synthesizing_target(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("return 'delete-calendar-event';", source)
        self.assertIn("never synthesizes arguments", source)
        self.assertNotIn("calendarDelete", source)

    def test_existing_verified_write_handoff_remains_for_unpromoted_mutations(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn(
            "resolveDeferredCalendarWriteAction(promotedSingleIntent) ??\n      explicitCalendarWriteIntent?.expectedAction",
            source,
        )
        self.assertIn("parseVerifiedCalendarWriteAction", source)
        self.assertIn(
            "interpretedCalendarWriteAction !== deferredCalendarWriteAction",
            source,
        )
        self.assertIn("Calendar write not safely resolved", source)
        self.assertIn("No calendar change was made.", source)

    def test_cross_capability_add_without_calendar_noun_is_not_claimed_by_frontend_fallback(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "/^(?:add|create|make|put|book)\\b/i.test(writeText) &&\n    CALENDAR_TARGET_TERM.test(writeText)",
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
        self.assertIn("if (!writeText || SCHEDULE_AS_NOUN_OR_READ.test(writeText)) return null;", source)

    def test_broad_schedule_planning_is_not_collapsed_into_one_calendar_event(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("BROAD_SCHEDULING_PLAN_TITLE", source)
        self.assertIn("(?:day|schedule|agenda|plans?)", source)
        self.assertIn("BROAD_SCHEDULING_PLAN_TITLE.test(targetWithoutNearTermDay)", source)

    def test_polite_explicit_calendar_write_prefix_is_normalized_before_classification(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarWriteIntent.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("(?:can|could|would|will)\\s+you\\s+(?:please\\s+)?", source)


if __name__ == "__main__":
    unittest.main()
