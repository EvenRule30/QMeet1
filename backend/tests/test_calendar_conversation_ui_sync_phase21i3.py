import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = REPO_ROOT / 'src' / 'app' / 'lib' / 'calendarUiContext.ts'
RANGE_PATH = REPO_ROOT / 'src' / 'app' / 'lib' / 'calendarReadRange.ts'
PANEL_PATH = REPO_ROOT / 'src' / 'app' / 'components' / 'CalendarPanel.tsx'


class CalendarConversationUiSyncPhase21I3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = HELPER_PATH.read_text(encoding='utf-8')
        cls.range_source = RANGE_PATH.read_text(encoding='utf-8')
        cls.panel = PANEL_PATH.read_text(encoding='utf-8')

    def test_context_hint_is_tab_scoped_and_one_shot(self):
        self.assertIn('window.sessionStorage.setItem', self.helper)
        self.assertIn('window.sessionStorage.removeItem', self.helper)
        self.assertIn('consumeCalendarPanelDateHint', self.helper)
        self.assertNotIn('localStorage', self.helper)

    def test_single_day_verified_range_read_seeds_panel_date(self):
        self.assertIn(
            'range.startDate === range.endDate',
            self.range_source,
        )
        self.assertIn(
            'rememberCalendarPanelDateHint(range.startDate)',
            self.range_source,
        )

    def test_multi_day_range_does_not_force_one_calendar_day(self):
        self.assertNotIn(
            'rememberCalendarPanelDateHint(range.endDate)',
            self.range_source,
        )

    def test_panel_consumes_hint_without_overwriting_it_on_mount(self):
        self.assertIn(
            'consumeCalendarPanelDateHint() ?? relativeViewDateKey',
            self.panel,
        )
        self.assertIn('const previousViewRef = useRef(view)', self.panel)
        self.assertIn('if (previousViewRef.current === view) return', self.panel)

    def test_calendar_navigation_remains_user_controlled_after_handoff(self):
        self.assertIn("handleRelativeViewSelection('today')", self.panel)
        self.assertIn("handleRelativeViewSelection('tomorrow')", self.panel)
        self.assertIn('type="date"', self.panel)


if __name__ == '__main__':
    unittest.main()
