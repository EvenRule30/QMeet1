from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
PROMOTION = (ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts").read_text(encoding="utf-8")
CONTINUATION = (ROOT / "backend" / "app" / "tool_continuation.py").read_text(encoding="utf-8")
CAPS = (ROOT / "backend" / "app" / "qmeet_capabilities.py").read_text(encoding="utf-8")


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
        self.assertIn("def _is_global_task_read_continuation", CONTINUATION)
        self.assertIn("if _is_global_task_read_continuation(request):", CONTINUATION)
        self.assertIn("search_owned or calendar_owned or global_task_read", CONTINUATION)

    def test_shared_contract_documents_global_task_read(self) -> None:
        self.assertIn('"promotedReadAction": "read-memory"', CAPS)
        self.assertIn('"scope": {"type": "string", "enum": ["global"]}', CAPS)

    def test_focus_task_completion_compatibility_seam_remains(self) -> None:
        self.assertIn("const confirmedTaskCommandMatch: CommandMatch | undefined =", APP)
        self.assertIn("confirmedTaskCommandMatch,", APP)


if __name__ == "__main__":
    unittest.main()
