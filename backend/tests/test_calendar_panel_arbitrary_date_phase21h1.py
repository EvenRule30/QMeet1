import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CALENDAR_PANEL = REPO_ROOT / "src" / "app" / "components" / "CalendarPanel.tsx"


class CalendarPanelArbitraryDatePhase21H1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CALENDAR_PANEL.read_text(encoding="utf-8")

    def test_panel_keeps_existing_relative_calendar_contract(self):
        self.assertIn("type CalendarView", self.source)
        self.assertIn("onViewChange: (view: CalendarView) => void", self.source)
        self.assertIn("handleRelativeViewSelection('today')", self.source)
        self.assertIn("handleRelativeViewSelection('tomorrow')", self.source)

    def test_panel_supports_previous_next_and_direct_date_navigation(self):
        self.assertIn('aria-label="Previous day"', self.source)
        self.assertIn('aria-label="Next day"', self.source)
        self.assertIn('type="date"', self.source)
        self.assertIn("shiftDateKey(selectedDateKey, -1)", self.source)
        self.assertIn("shiftDateKey(selectedDateKey, 1)", self.source)

    def test_absolute_dates_use_existing_canonical_range_read(self):
        self.assertIn(
            "import { fetchCalendarEventsRange } from '../lib/calendarReadRange';",
            self.source,
        )
        self.assertIn("startDate: selectedDateKey", self.source)
        self.assertIn("endDate: selectedDateKey", self.source)
        self.assertIn("setRangeGoogleEvents(response.events)", self.source)

    def test_arbitrary_date_google_deletes_remain_behind_qmeet_safety_path(self):
        self.assertIn(
            "googleStatus?.writeEnabled && selectedRelativeView",
            self.source,
        )
        self.assertIn(
            "Use QMeet for edits or deletions on this selected date",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
