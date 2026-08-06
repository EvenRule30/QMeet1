from __future__ import annotations

import re
import unittest
from pathlib import Path


class FocusCanonicalReadReconciliationPhase20J0Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.reconciliation_source = (
            root / "src/app/lib/canonicalFocusProjection.ts"
        ).read_text(encoding="utf-8")

    def test_canonical_state_controls_whether_projection_is_active(self) -> None:
        source = self.reconciliation_source
        for status in ("clarifying", "active", "waiting", "ready"):
            self.assertIn(f"'{status}'", source)
        self.assertNotIn("'complete',\n]);", source)
        self.assertIn("if (!isCanonicalFocusOpen(state))", source)
        self.assertIn("return null;", source)

    def test_projection_identity_and_goal_come_from_canonical_state(self) -> None:
        source = self.reconciliation_source
        self.assertIn("id: state.focusId.trim()", source)
        self.assertIn("const title = state.title.trim()", source)
        self.assertIn("const goal = state.objective.trim()", source)
        self.assertIn("startedAt: state.createdAt.trim()", source)
        self.assertIn("updatedAt: state.updatedAt.trim()", source)

    def test_memory_metadata_is_preserved_only_for_same_focus_id(self) -> None:
        source = self.reconciliation_source
        self.assertIn("if (currentSession?.id === focusId)", source)
        self.assertIn(
            "recentSessions.find((session) => session.id === focusId)",
            source,
        )
        self.assertIn("linkedTaskIds: exactSource?.linkedTaskIds ?? []", source)
        self.assertIn("pinnedNoteIds: exactSource?.pinnedNoteIds ?? []", source)
        self.assertNotIn("currentSession?.linkedTaskIds ?? []", source)

    def test_reconciliation_updates_browser_projection_without_legacy_write(self) -> None:
        source = self.reconciliation_source
        self.assertIn("qmeet-active-session", source)
        self.assertIn("qmeet-active-session-live", source)
        self.assertIn("qmeet-active-session-state", source)
        self.assertIn("window.localStorage.removeItem", source)
        self.assertIn("window.sessionStorage.removeItem", source)
        self.assertNotIn("replaceActiveSession", source)
        self.assertNotIn("clearActiveSession(", source)
        self.assertNotIn("/api/memory/session", source)

    def test_app_reconciles_after_memory_hydration_and_before_routing(self) -> None:
        app = self.app_source
        self.assertIn(
            "import { reconcileCanonicalFocusProjection } from './lib/canonicalFocusProjection';",
            app,
        )
        self.assertIn("recentFocusSessions,", app)
        self.assertIn("const reconcileFocusProjection = useCallback(async () =>", app)
        self.assertIn("void reconcileFocusProjection();", app)

        reconcile_position = app.index("const routingActiveSession =")
        terminal_position = app.index("const directFocusTerminalCommandMatch =")
        parser_position = app.index(
            "const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);"
        )
        self.assertLess(reconcile_position, terminal_position)
        self.assertLess(terminal_position, parser_position)

    def test_natural_task_completion_uses_reconciled_focus(self) -> None:
        app = self.app_source
        natural_block = re.search(
            r"const naturalTaskCompletionTarget\s*=([\s\S]+?)"
            r"const naturalTaskCompletionCommandMatch",
            app,
        )
        self.assertIsNotNone(natural_block)
        block = natural_block.group(1) if natural_block else ""
        self.assertIn("routingActiveSession", block)
        self.assertNotIn("\n            activeSession,", block)

    def test_reconciliation_failure_preserves_current_projection(self) -> None:
        app = self.app_source
        self.assertIn(
            "Canonical Focus projection reconciliation failed; preserving the current projection.",
            app,
        )
        self.assertIn("return activeSession;", app)


if __name__ == "__main__":
    unittest.main()
