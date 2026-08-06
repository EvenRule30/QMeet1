from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND = REPO_ROOT / "src" / "app" / "lib" / "semanticFocusLifecycle.ts"
BACKEND = REPO_ROOT / "backend" / "app" / "focus" / "semantic_lifecycle_preflight.py"


class SemanticFocusLifecycleCompatibilityPhase20I3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frontend = FRONTEND.read_text(encoding="utf-8")
        cls.backend = BACKEND.read_text(encoding="utf-8")

    def test_frontend_and_backend_bridge_versions_match_phase20d2b1(self) -> None:
        frontend_match = re.search(
            r"SEMANTIC_(?:FOCUS_)?LIFECYCLE_BRIDGE_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
            self.frontend,
        )
        backend_match = re.search(
            r"SEMANTIC_(?:FOCUS_)?LIFECYCLE_BRIDGE_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
            self.backend,
        )
        self.assertIsNotNone(frontend_match)
        self.assertIsNotNone(backend_match)
        self.assertEqual(frontend_match.group(1), "phase20d2b1")
        self.assertEqual(frontend_match.group(1), backend_match.group(1))

    def test_task_completion_only_defers_for_focus_terminal_language(self) -> None:
        self.assertIn("commandMatch?.command === 'mark-task-done'", self.frontend)
        self.assertIn(
            "looksLikeFocusTerminalLanguage(originalMessage)",
            self.frontend,
        )

    def test_terminal_detector_preserves_focus_target_safety_contract(self) -> None:
        self.assertIn("const directFocusTerminalPattern", self.frontend)
        self.assertIn("const focusTarget", self.frontend)
        self.assertIn("const focusReference", self.frontend)
        self.assertIn("const terminalLanguage", self.frontend)
        self.assertIn("focusTarget && terminalLanguage", self.frontend)

    def test_all_exact_lifecycle_mutations_remain_deferred(self) -> None:
        for command in (
            "start-focus-session",
            "update-focus-session",
            "resume-last-focus-session",
            "end-focus-session",
            "end-focus-with-summary",
        ):
            self.assertIn(
                f"commandMatch?.command === '{command}'",
                self.frontend,
            )

    def test_explicit_typed_start_command_is_preserved(self) -> None:
        self.assertIn("command: 'start-focus-session'", self.frontend)

    def test_end_complete_summary_and_phase20i_context_coexist(self) -> None:
        for marker in (
            "payload.intent === 'end'",
            "payload.intent === 'complete'",
            "payload.summaryRequired === true",
            "phase20i-context:",
            "return looksLikeFocusTerminalLanguage(message);",
        ):
            self.assertIn(marker, self.frontend)


if __name__ == "__main__":
    unittest.main()
