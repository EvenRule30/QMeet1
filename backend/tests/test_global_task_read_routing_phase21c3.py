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


def assert_confirmed_task_identity_path(
    testcase: unittest.TestCase,
    source: str,
) -> None:
    capture = source.index(
        "const resolvedTaskTargets = pendingTaskCompletionTargetsRef.current;"
    )
    synthetic = source.index(
        "const confirmedTaskCommandMatch: CommandMatch | undefined =",
        capture,
    )
    wrapper = source.index(
        "const executeConfirmedPendingCommand = async (",
        synthetic,
    )
    confirmed_call = source.index("await handleSend(", wrapper)
    confirmed_end = source.index(");", confirmed_call)
    call_block = source[confirmed_call:confirmed_end]

    testcase.assertLess(capture, synthetic)
    testcase.assertLess(synthetic, wrapper)
    testcase.assertIn("confirmedCommandMatch", call_block)
    testcase.assertIn("resolvedTaskTargets", call_block)
    testcase.assertIn("'confirmed'", call_block)


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

    def test_continuation_excludes_focus_for_global_task_scope(self) -> None:
        self.assertIn(
            "def _is_explicit_global_task_continuation",
            CONTINUATION,
        )
        self.assertIn(
            'return "qmeetScope=global-tasks" in request.toolContext',
            CONTINUATION,
        )
        self.assertIn(
            "if _is_explicit_global_task_continuation(request):",
            CONTINUATION,
        )
        self.assertIn(
            "global_tasks_owned = _is_explicit_global_task_continuation(request)",
            CONTINUATION,
        )
        self.assertIn(
            "if global_tasks_owned:",
            CONTINUATION,
        )

        global_block_start = CONTINUATION.index("if global_tasks_owned:")
        global_block_end = CONTINUATION.index(
            "elif isolate_stale_conversation:",
            global_block_start,
        )
        global_block = CONTINUATION[global_block_start:global_block_end]
        self.assertIn("pass", global_block)
        self.assertNotIn("_request_recent_history(request)", global_block)
        self.assertNotIn("_request_recent_tool_updates(request)", global_block)

    def test_backward_compatible_read_detector_still_exists(self) -> None:
        self.assertIn(
            "def _is_global_task_read_continuation",
            CONTINUATION,
        )
        self.assertIn(
            'request.action.strip().casefold() == "read-memory"',
            CONTINUATION,
        )
        self.assertIn(
            "_is_explicit_global_task_continuation(request)",
            CONTINUATION,
        )

    def test_shared_contract_documents_global_task_read(self) -> None:
        self.assertIn('"promotedReadAction": "read-memory"', CAPS)
        self.assertIn(
            '"scope": {"type": "string", "enum": ["global"]}',
            CAPS,
        )

    def test_focus_task_completion_compatibility_seam_remains(self) -> None:
        assert_confirmed_task_identity_path(self, APP)


if __name__ == "__main__":
    unittest.main()
