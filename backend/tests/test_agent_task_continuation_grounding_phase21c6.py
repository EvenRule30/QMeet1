from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "app" / "App.tsx"
TOOL_CONTINUATION = ROOT / "backend" / "app" / "tool_continuation.py"


class AgentTaskContinuationGroundingPhase21C6Tests(unittest.TestCase):
    def test_global_task_creation_explicitly_denies_focus_relationship(self):
        source = APP.read_text(encoding="utf-8")

        self.assertIn(
            "qmeetScope=global-tasks. qmeetFocusRelationship=none. "
            "This task creation was verified by the canonical backend task endpoint "
            "and created one global task only.",
            source,
        )
        self.assertIn(
            "No Active Focus task relationship was created or verified by this operation.",
            source,
        )
        self.assertIn(
            "Do not describe this task as linked to or part of the Active Focus.",
            source,
        )

    def test_confirmed_task_completion_distinguishes_global_from_focus_linked(self):
        source = APP.read_text(encoding="utf-8")
        start = source.index(
            "const confirmedTaskCommandResult: SplitCommandResult ="
        )
        end = source.index(
            "const globalTaskReadCommandResult: SplitCommandResult =",
            start,
        )
        block = source[start:end]

        self.assertIn("focusTaskProgressResult?.verified", block)
        self.assertIn("confirmedFocusTaskTargets.length > 0", block)
        self.assertIn(
            "qmeetScope=focus-linked-task. qmeetFocusRelationship=verified.",
            block,
        )
        self.assertIn(
            "qmeetScope=global-tasks. qmeetFocusRelationship=none.",
            block,
        )
        self.assertIn(
            "No Active Focus task relationship or Focus progress was created or verified",
            block,
        )

    def test_focus_link_claim_requires_canonical_progress_verification(self):
        source = APP.read_text(encoding="utf-8")
        start = source.index(
            "const confirmedTaskCommandResult: SplitCommandResult ="
        )
        end = source.index(
            "const globalTaskReadCommandResult: SplitCommandResult =",
            start,
        )
        block = source[start:end]

        verified_check = block.index("focusTaskProgressResult?.verified")
        linked_target_check = block.index("confirmedFocusTaskTargets.length > 0")
        verified_marker = block.index("qmeetFocusRelationship=verified")

        self.assertLess(verified_check, verified_marker)
        self.assertLess(linked_target_check, verified_marker)

    def test_task_relationship_context_reaches_tool_continuation(self):
        source = APP.read_text(encoding="utf-8")

        self.assertIn(
            "confirmedTaskCommandResult.handled",
            source,
        )
        self.assertIn(
            "? confirmedTaskCommandResult",
            source,
        )
        self.assertIn(
            "toolContext: splitCommandResult.continuationContext,",
            source,
        )

    def test_backend_continuation_contract_forbids_unverified_state_claims(self):
        source = TOOL_CONTINUATION.read_text(encoding="utf-8")

        self.assertIn(
            "Never claim that Focus, Calendar, Memory, tasks, notes, or any other state changed beyond the verified receipt.",
            source,
        )
        self.assertIn(
            '"verifiedToolContext": request.toolContext or ""',
            source,
        )


if __name__ == "__main__":
    unittest.main()
