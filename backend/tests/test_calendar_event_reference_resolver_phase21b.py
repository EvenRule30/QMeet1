from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class CalendarEventReferenceResolverPhase21BTests(unittest.TestCase):
    def test_resolver_has_exact_likely_ambiguous_and_none_outcomes(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarEventResolver.ts"
        ).read_text(encoding="utf-8")
        for outcome in ("'exact'", "'likely'", "'ambiguous'", "'none'"):
            with self.subTest(outcome=outcome):
                self.assertIn(outcome, source)
        self.assertIn("LIKELY_MATCH_THRESHOLD = 0.82", source)
        self.assertIn("LIKELY_MATCH_MARGIN = 0.08", source)

    def test_resolver_uses_normalized_title_similarity_and_time_as_hard_filter(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarEventResolver.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("normalizeReferenceTitle", source)
        self.assertIn("levenshteinDistance", source)
        self.assertIn("tokenCoverage", source)
        self.assertIn("eventMatchesRequestedTime", source)
        self.assertIn("isEventForCalendarView", source)
        self.assertIn("TITLE_STOP_WORDS", source)

    def test_resolver_never_accepts_or_returns_model_event_identity(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "calendarEventResolver.ts"
        ).read_text(encoding="utf-8")
        criteria_section = source[source.index("export type CalendarEventReferenceCriteria"):source.index("export type CalendarEventReferenceResolution")]
        self.assertNotIn("eventId", criteria_section)
        self.assertNotIn("googleEventId", criteria_section)

    def test_app_shares_resolver_between_edit_and_delete(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("resolveCalendarEventReference("), 2)
        self.assertIn("query: promotedCalendarEditTargetCriteria.query", source)
        self.assertIn("query: commandMatch.calendarDelete?.title ?? null", source)
        self.assertIn("Did you mean this event?", source)
        self.assertIn("Which one did you mean?", source)

    def test_likely_match_still_locks_real_event_identity_before_mutation(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("pendingCalendarEditTargetIdRef.current = targetEditEvent.id", source)
        self.assertIn("pendingCalendarDeleteTargetIdRef.current", source)
        self.assertIn("targetDeleteEvent.id", source)
        self.assertIn("resolvedCalendarEditTargetId", source)
        self.assertIn("resolvedCalendarDeleteTargetId", source)


if __name__ == "__main__":
    unittest.main()
