from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "src" / "app" / "panels" / "StatusOverlay.tsx"
CSS = ROOT / "src" / "app" / "panels" / "StatusOverlay.css"


class StatusPanelRemasterPhase21H3Tests(unittest.TestCase):
    def test_status_panel_keeps_high_value_everyday_signals(self):
        source = STATUS.read_text(encoding="utf-8")

        for expected in (
            "QMeet system",
            "At a glance",
            "What QMeet is holding",
            "Last interaction",
            "statusGoogleCalendarLabel",
            "statusOpenTasksCount",
            "statusNotesCount",
            "searchStatusLabel",
            "pendingInterpreterLabel",
        ):
            self.assertIn(expected, source)

    def test_status_panel_drops_development_era_dashboard_noise(self):
        source = STATUS.read_text(encoding="utf-8")

        for removed in (
            "FocusResponseHealth",
            "Max output tokens",
            "OpenAI key",
            "Supported Status Commands",
            "Local Storage",
            "Mapped Command",
            "Pending Confirm",
            "Normalized:",
        ):
            self.assertNotIn(removed, source)

    def test_status_remaster_uses_scoped_styles(self):
        source = STATUS.read_text(encoding="utf-8")
        css = CSS.read_text(encoding="utf-8")

        self.assertIn("import './StatusOverlay.css';", source)
        self.assertIn("status-remaster-grid", source)
        self.assertIn(".status-remaster-grid", css)
        self.assertIn("@media (max-width: 1100px), (max-height: 650px)", css)


if __name__ == "__main__":
    unittest.main()
