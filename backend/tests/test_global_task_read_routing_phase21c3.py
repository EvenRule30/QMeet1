from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
PROMOTION = (
    ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
).read_text(encoding="utf-8")
CONTINUATION = (
    ROOT / "backend" / "app" / "tool_continuation.py"
).read_text(encoding="utf-8")
CAPS = (
    ROOT / "backend" / "app" / "qmeet_capabilities.py"
).read_text(encoding="utf-8")


class GlobalTaskReadRoutingPhase21C3Tests(unittest.TestCase):
    def test_frontend_validates_global_scope(self) -> None:
        self.assertIn("argumentsValue.scope === 'global'", PROMOTION)
        self.assertIn("decision.proposedAction === 'read-memory'", PROMOTION)
        self.assertIn("isExplicitGlobalTaskReadRequest", PROMOTION)
        self.assertIn("FOCUS_TASK_REFERENCE", PROMOTION)

    def test_exact_task_read_defers_legacy_read_memory_ambiguity(self) -> None:
        self.assertIn("const explicitGlobalTaskReadRequest =", APP)
        self.assertIn("!explicitGlobalTaskReadRequest", APP)
        self.assertIn("Deterministic global task read ownership floor", APP)

    def test_global_read_uses_authoritative_task_formatter(self) -> None:
        self.assertIn("formatOpenTasksReadout(memoryTasks)", APP)
        self.assertIn("qmeetScope=global-tasks", APP)
        self.assertIn("'tool'", APP)

    def test_continuation_excludes_focus_for_verified_global_task_scope(self) -> None:
        # Phase 21C3 introduced read-only global-task isolation. Phase 21D1B
        # broadens the same ownership rule to verified global task
        # create/read/complete/delete continuations. Keep the historical helper
        # as a compatibility wrapper, but assert the stronger scope invariant.
        self.assertIn(
            "def _is_explicit_global_task_continuation",
            CONTINUATION,
        )
        self.assertIn(
            "def _is_global_task_read_continuation",
            CONTINUATION,
        )
        self.assertIn(
            "and _is_explicit_global_task_continuation(request)",
            CONTINUATION,
        )

        focus_relevance = CONTINUATION.index(
            "def focus_context_relevant_to_continuation("
        )
        recent_history = CONTINUATION.index(
            "def _fallback_recent_history()",
            focus_relevance,
        )
        focus_block = CONTINUATION[focus_relevance:recent_history]
        self.assertIn(
            "if _is_explicit_global_task_continuation(request):",
            focus_block,
        )
        self.assertIn("return False", focus_block)

        build_input = CONTINUATION.index(
            "def build_tool_continuation_input("
        )
        record_history = CONTINUATION.index(
            "def _record_history(",
            build_input,
        )
        build_block = CONTINUATION[build_input:record_history]
        self.assertIn(
            "global_tasks_owned = _is_explicit_global_task_continuation(request)",
            build_block,
        )
        self.assertIn("if global_tasks_owned:", build_block)

        # Global Tasks must not inherit stale recent conversation or prior tool
        # cards after deterministic scope explicitly says qmeetScope=global-tasks.
        global_branch = build_block[
            build_block.index("if global_tasks_owned:"):
            build_block.index("elif isolate_stale_conversation:")
        ]
        self.assertNotIn("_request_recent_history(request)", global_branch)
        self.assertNotIn("_request_recent_tool_updates(request)", global_branch)

    def test_shared_contract_documents_global_task_read(self) -> None:
        self.assertIn('"promotedReadAction": "read-memory"', CAPS)
        self.assertIn(
            '"scope": {"type": "string", "enum": ["global"]}',
            CAPS,
        )

    def test_focus_task_completion_compatibility_seam_remains(self) -> None:
        self.assertIn(
            "const confirmedTaskCommandMatch: CommandMatch | undefined =",
            APP,
        )
        self.assertIn("confirmedTaskCommandMatch,", APP)


if __name__ == "__main__":
    unittest.main()
