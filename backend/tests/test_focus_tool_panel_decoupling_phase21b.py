from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
APP_PATH = ROOT / "src" / "app" / "App.tsx"


class FocusToolPanelDecouplingPhase21BTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_source = APP_PATH.read_text(encoding="utf-8")

    def test_focus_commands_preserve_current_panel_instead_of_opening_memory(self):
        expected_commands = (
            "start-focus-session",
            "update-focus-session",
            "resume-last-focus-session",
            "end-focus-session",
            "end-focus-with-summary",
            "wrap-up-meeting-focus",
            "save-focus-summary",
            "focus-to-tasks",
            "create-meeting-follow-up-tasks",
            "prepare-calendar-focus",
            "read-focus-session",
            "summarize-focus-session",
        )
        self.assertIn("FOCUS_COMMANDS_THAT_PRESERVE_ACTIVE_PANEL", self.app_source)
        for command in expected_commands:
            self.assertIn(f"'{command}'", self.app_source)

    def test_only_legacy_memory_open_is_suppressed(self):
        self.assertIn("panel === 'memory'", self.app_source)
        self.assertIn(
            "FOCUS_COMMANDS_THAT_PRESERVE_ACTIVE_PANEL.has(command)",
            self.app_source,
        )
        self.assertIn("setActivePanel(panel);", self.app_source)

    def test_memory_handler_receives_filtered_panel_setter(self):
        self.assertIn(
            "setActivePanel: setPanelForMemoryCommand",
            self.app_source,
        )
        self.assertIn(
            "shouldSuppressLegacyFocusMemoryOpen(commandMatch.command, panel)",
            self.app_source,
        )

    def test_explicit_memory_read_is_not_suppressed(self):
        focus_set_block = self.app_source.split(
            "const FOCUS_COMMANDS_THAT_PRESERVE_ACTIVE_PANEL",
            1,
        )[1].split("]);", 1)[0]
        self.assertNotIn("'read-memory'", focus_set_block)

    def test_focus_history_read_is_still_allowed_to_open_memory(self):
        focus_set_block = self.app_source.split(
            "const FOCUS_COMMANDS_THAT_PRESERVE_ACTIVE_PANEL",
            1,
        )[1].split("]);", 1)[0]
        self.assertNotIn("'read-focus-history'", focus_set_block)

    def test_non_memory_destinations_are_not_blocked(self):
        helper_block = self.app_source.split(
            "function shouldSuppressLegacyFocusMemoryOpen",
            1,
        )[1].split("export default function App", 1)[0]
        self.assertNotIn("panel === 'calendar'", helper_block)
        self.assertNotIn("panel === 'notes'", helper_block)


if __name__ == "__main__":
    unittest.main()
