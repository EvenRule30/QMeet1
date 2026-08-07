from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "app" / "App.tsx"
HELPER = ROOT / "src" / "app" / "lib" / "confirmedTaskCompletion.ts"


class FocusTaskCompletionAtomicCommitPhase20QTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = APP.read_text(encoding="utf-8")
        cls.helper = HELPER.read_text(encoding="utf-8")

    def test_linked_focus_completion_verifies_before_local_projection(self) -> None:
        verify_index = self.app.index("await recordVerifiedFocusTaskProgress(")
        local_index = self.app.index("completeConfirmedTaskTargets(", verify_index)
        self.assertLess(verify_index, local_index)

    def test_failed_focus_verification_returns_before_local_completion(self) -> None:
        failure_text = (
            "I could not verify the linked Focus task completion, so no task was changed. "
            "Make sure the QMeet backend is running and try again."
        )
        failure_index = self.app.index(failure_text)
        return_index = self.app.index("return;", failure_index)
        local_index = self.app.index("completeConfirmedTaskTargets(", return_index)
        self.assertLess(failure_index, return_index)
        self.assertLess(return_index, local_index)
        self.assertNotIn(
            "The task was completed, but canonical Focus progress could not be verified.",
            self.app,
        )

    def test_verified_backend_timestamp_is_mirrored_locally(self) -> None:
        self.assertIn("verifiedCompletedAtByTaskId", self.app)
        self.assertIn("focusTaskProgressResult?.tasks ?? []", self.app)
        self.assertIn("verifiedCompletedAtByTaskId", self.helper)
        self.assertIn(
            "verifiedCompletedAtByTaskId.get(task.id)?.trim()",
            self.helper,
        )

    def test_unlinked_task_completion_still_has_local_fallback(self) -> None:
        self.assertIn(
            "completeConfirmedTaskTargets(\n              memoryTasks,\n              confirmedTaskTargets,",
            self.app,
        )
        self.assertIn("const fallbackCompletedAt = new Date().toISOString();", self.helper)


if __name__ == "__main__":
    unittest.main()
