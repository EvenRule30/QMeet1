from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE_SOURCE = REPO_ROOT / "src" / "app" / "lib" / "semanticFocusLifecycle.ts"


class SemanticFocusLifecycleCompatibilityPhase20I1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = BRIDGE_SOURCE.read_text(encoding="utf-8")

    def test_version_handshake_and_phase20i_context_both_remain_installed(self):
        self.assertRegex(
            self.source,
            r"SEMANTIC_FOCUS_LIFECYCLE_BRIDGE_VERSION\s*=\s*['\"]phase20d2b1['\"]",
        )
        self.assertIn("payload.bridgeVersion !== SEMANTIC_FOCUS_LIFECYCLE_BRIDGE_VERSION", self.source)
        self.assertIn("phase20i-context:", self.source)

    def test_terminal_language_gate_requires_reference_and_terminal_word(self):
        detector = re.search(
            r"function looksLikeFocusTerminalLanguage\(message: string\): boolean \{(?P<body>.*?)\n\}",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(detector)
        body = detector.group("body")
        self.assertIn("focusTarget", body)
        self.assertIn("focusReference", body)
        self.assertIn("terminalLanguage", body)
        self.assertIn("focusTarget && terminalLanguage", body)
        self.assertIn("return looksLikeFocusTerminalLanguage(message);", self.source)

    def test_exact_route_precedence_keeps_task_and_lifecycle_compatibility(self):
        for marker in (
            "commandMatch?.command === 'mark-task-done'",
            "commandMatch?.command === 'start-focus-session'",
            "commandMatch?.command === 'update-focus-session'",
            "commandMatch?.command === 'resume-last-focus-session'",
            "commandMatch?.command === 'end-focus-session'",
            "commandMatch?.command === 'end-focus-with-summary'",
        ):
            self.assertIn(marker, self.source)

    def test_end_complete_summary_and_cancellation_contracts_remain_present(self):
        for marker in (
            "payload.intent === 'end'",
            "payload.intent === 'complete'",
            "payload.summaryRequired === true",
            "payload.intent === 'cancelled'",
            "command: 'end-focus-session'",
        ):
            self.assertIn(marker, self.source)

    def test_context_updates_still_use_verified_update_command_envelope(self):
        self.assertIn("contextEnvelopeFromReason", self.source)
        self.assertIn("contextField", self.source)
        self.assertIn("contextValue", self.source)
        self.assertIn("command: 'update-focus-session'", self.source)
        self.assertIn("sourceTurnId", self.source)


if __name__ == "__main__":
    unittest.main()
