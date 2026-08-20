from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "app" / "App.tsx"


class FocusTaskReadToolCardCompletePhase21C6DTests(unittest.TestCase):
    def test_focus_task_read_remains_canonical_and_verified(self) -> None:
        source = APP.read_text(encoding="utf-8")

        self.assertIn("commandMatch.payload === 'focus-task-read'", source)
        self.assertIn(
            "await reconcileCanonicalFocusProjection(",
            source,
        )
        self.assertIn("const authoritativeTasks = await getMemoryTasks();", source)
        self.assertIn(
            "confirmationContent: formatFocusTaskReadout(",
            source,
        )
        self.assertIn(
            "qmeetFocusTaskReadVerified=true",
            source,
        )

    def test_focus_task_read_tool_card_suppresses_model_continuation(self) -> None:
        source = APP.read_text(encoding="utf-8")

        marker = source.index("const focusTaskReadToolCardIsComplete =")
        continuation = source.index("await continueAfterVerifiedToolUpdate({", marker)
        block = source[marker:continuation]

        self.assertIn(
            "commandMatch.command === 'read-memory'",
            block,
        )
        self.assertIn(
            "commandMatch.payload === 'focus-task-read'",
            block,
        )
        self.assertIn(
            "if (!focusTaskReadToolCardIsComplete && !compositeAtomicExecution)",
            block,
        )

    def test_other_verified_tools_still_use_post_tool_continuation(self) -> None:
        source = APP.read_text(encoding="utf-8")

        self.assertIn(
            "await continueAfterVerifiedToolUpdate({",
            source,
        )
        self.assertIn(
            "toolContext: splitCommandResult.continuationContext",
            source,
        )

    def test_focus_task_read_tool_card_still_records_and_speaks_receipt(self) -> None:
        source = APP.read_text(encoding="utf-8")

        marker = source.index("const focusTaskReadToolCardIsComplete =")
        preceding = source[max(0, marker - 1800):marker]

        self.assertIn("const confirmationMsg = createAssistantMessage", preceding)
        self.assertIn("pushResultToast(", preceding)
        self.assertIn("speakAssistantText(", preceding)


if __name__ == "__main__":
    unittest.main()
