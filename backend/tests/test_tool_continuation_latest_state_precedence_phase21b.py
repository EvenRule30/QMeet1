from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOL_CONTINUATION = (
    ROOT / "backend" / "app" / "tool_continuation.py"
).read_text(encoding="utf-8")


class ToolContinuationLatestStatePrecedencePhase21BTests(unittest.TestCase):
    def test_verified_receipt_is_declared_newer_than_recent_history(self) -> None:
        self.assertIn("Latest-state precedence:", TOOL_CONTINUATION)
        self.assertIn(
            "verified tool receipt and current canonical state are newer than recentConversation",
            TOOL_CONTINUATION,
        )

    def test_focus_update_must_center_on_just_changed_state(self) -> None:
        self.assertIn(
            "After a verified Focus update, center the response on what was just changed.",
            TOOL_CONTINUATION,
        )
        self.assertIn(
            "do not continue an older subtopic unless it directly advances the newly verified state",
            TOOL_CONTINUATION,
        )

    def test_old_focus_objective_cannot_override_verified_new_objective(self) -> None:
        self.assertIn(
            "Never answer as though an earlier Focus objective is still current",
            TOOL_CONTINUATION,
        )
        self.assertIn("verifiedToolReceipt", TOOL_CONTINUATION)
        self.assertIn("activeFocusAdvisoryContext", TOOL_CONTINUATION)

    def test_latest_receipt_remains_last_model_input(self) -> None:
        history_index = TOOL_CONTINUATION.index(
            "messages.extend(_request_recent_history(request))"
        )
        payload_index = TOOL_CONTINUATION.index(
            '"Continue from the verified QMeet tool update below.', history_index
        )
        self.assertLess(history_index, payload_index)


if __name__ == "__main__":
    unittest.main()
