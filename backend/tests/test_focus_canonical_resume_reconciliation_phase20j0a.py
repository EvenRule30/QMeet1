from __future__ import annotations

import re
import unittest
from pathlib import Path


class FocusCanonicalResumeReconciliationPhase20J0ATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.reconciliation_source = (
            root / "src/app/lib/canonicalFocusProjection.ts"
        ).read_text(encoding="utf-8")

    def test_reconciliation_does_not_write_retired_memory_projection(self) -> None:
        source = self.reconciliation_source
        self.assertIn("applyActiveSessionProjection(nextSession);", source)
        self.assertNotIn("replaceActiveSession", source)
        self.assertNotIn("clearActiveSession", source)
        self.assertNotIn("/api/memory/session", source)

    def test_exact_resume_receives_deterministic_lifecycle_preflight(self) -> None:
        app = self.app_source
        self.assertIn("const exactResumeLifecyclePreflight =", app)
        self.assertIn(
            "deferredExactFocusLifecycleMatch?.command === 'resume-last-focus-session'",
            app,
        )
        self.assertIn("kind: 'resume' as const", app)
        self.assertIn("commandMatch: deferredExactFocusLifecycleMatch", app)
        self.assertIn(
            "exactResumeLifecyclePreflight ??\n          await interpretSemanticFocusLifecycle(trimmed)",
            app,
        )

    def test_resume_still_uses_deferred_verified_command_path(self) -> None:
        app = self.app_source
        parse_position = app.index(
            "const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);"
        )
        defer_position = app.index("const deferredExactFocusLifecycleMatch =")
        resume_preflight_position = app.index("const exactResumeLifecyclePreflight =")
        semantic_position = app.index(
            "const semanticLifecyclePreflightBeforeCommandRouting ="
        )
        selection_position = app.index("const commandMatch =")
        self.assertLess(parse_position, defer_position)
        self.assertLess(defer_position, resume_preflight_position)
        self.assertLess(resume_preflight_position, semantic_position)
        self.assertLess(semantic_position, selection_position)

    def test_resume_is_routed_to_existing_native_command_handler(self) -> None:
        app = self.app_source
        lifecycle_condition = re.search(
            r"if \(\n\s+semanticFocusLifecycle\.kind === 'update'[\s\S]+?\n\s+\) \{",
            app,
        )
        self.assertIsNotNone(lifecycle_condition)
        block = lifecycle_condition.group(0) if lifecycle_condition else ""
        self.assertIn("semanticFocusLifecycle.kind === 'resume'", block)
        self.assertIn("resume: {", app)
        self.assertIn("action: 'resume_focus_session'", app)
        self.assertIn("frontendCommand: 'apply verified focus resume'", app)
        self.assertIn("semanticFocusLifecycle.commandMatch,", app)

    def test_other_lifecycle_messages_still_use_semantic_endpoint(self) -> None:
        app = self.app_source
        self.assertIn("await interpretSemanticFocusLifecycle(trimmed)", app)
        self.assertIn(
            "shouldPreflightSemanticFocusLifecycleBeforeCommandRouting(trimmed)",
            app,
        )

    def test_direct_terminal_gate_still_precedes_resume_and_parser_routing(self) -> None:
        app = self.app_source
        terminal_position = app.index("const directFocusTerminalCommandMatch =")
        parser_position = app.index(
            "const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);"
        )
        resume_position = app.index("const exactResumeLifecyclePreflight =")
        self.assertLess(terminal_position, parser_position)
        self.assertLess(parser_position, resume_position)


if __name__ == "__main__":
    unittest.main()
