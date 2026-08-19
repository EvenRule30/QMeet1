from __future__ import annotations

from pathlib import Path
import unittest

from app.tool_continuation import TOOL_CONTINUATION_PROMPT


ROOT = Path(__file__).resolve().parents[2]


class CalendarContinuationGroundingPhase21F5Tests(unittest.TestCase):
    def test_calendar_edit_receipt_carries_verified_post_write_date_time_and_title(self) -> None:
        source = (
            ROOT / "src/app/commandHandlers/calendar.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("formatVerifiedCalendarEvent(updatedEvent)", source)
        self.assertIn("buildVerifiedCalendarEditContinuationContext(updatedEvent)", source)
        self.assertIn("verifiedEventDate=${event.dateKey}", source)
        self.assertIn("verifiedEventTime=${event.time}", source)
        self.assertIn("verifiedEventTitle=${JSON.stringify(event.title)}", source)
        self.assertIn(
            "Do not reconstruct or shorten the destination date from the original user wording.",
            source,
        )

    def test_targeted_delete_receipt_also_carries_verified_deleted_event_identity(self) -> None:
        source = (
            ROOT / "src/app/commandHandlers/calendar.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("buildVerifiedCalendarDeleteContinuationContext(deletedEvent)", source)
        self.assertIn("verifiedDeletedEventDate=${event.dateKey}", source)
        self.assertIn("verifiedDeletedEventTime=${event.time}", source)
        self.assertIn("verifiedDeletedEventTitle=${JSON.stringify(event.title)}", source)

    def test_calendar_continuation_does_not_introduce_focus_without_verified_relevance(self) -> None:
        self.assertIn(
            "For a Calendar-owned continuation when focusContextIncluded is false",
            TOOL_CONTINUATION_PROMPT,
        )
        self.assertIn(
            "do not mention Focus, Focus tasks, Focus goals, or returning to Focus",
            TOOL_CONTINUATION_PROMPT,
        )


if __name__ == "__main__":
    unittest.main()
