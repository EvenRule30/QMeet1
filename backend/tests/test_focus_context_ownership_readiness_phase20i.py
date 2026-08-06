from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus.ownership import get_native_focus_ownership_readiness


_QUARANTINED = [
    "start-focus-session",
    "update-focus-session",
    "resume-last-focus-session",
    "end-focus-session",
    "end-focus-with-summary",
    "wrap-up-meeting-focus",
    "save-focus-summary",
    "focus-to-tasks",
    "create-meeting-follow-up-tasks",
    "prepare-calendar-focus",
]


def _health_section(outcome: str = "verified", *, attempts: int = 1) -> dict[str, object]:
    failed = outcome == "failed"
    return {
        "attemptCount": attempts,
        "verifiedCount": 0 if failed or attempts == 0 else attempts,
        "failedCount": 1 if failed else 0,
        "lastOutcome": "failed" if failed else ("added" if attempts else ""),
        "lastFailureCode": "verification_failed" if failed else "",
        "lastUpdatedAt": "2026-08-05T17:10:00-07:00" if attempts else "",
    }


class FocusContextOwnershipReadinessPhase20ITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self._write_source_contract()
        self.repo_patch = patch.dict(os.environ, {"QMEET_REPO_ROOT": str(self.root)})
        self.repo_patch.start()
        self.addCleanup(self.repo_patch.stop)

    def _write(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _write_source_contract(self) -> None:
        self._write("src/app/hooks/useCalendarController.ts", "export const calendarOnly = true;\n")
        self._write(
            "backend/app/routers/memory.py",
            "\n".join(
                [
                    "FOCUS_PROJECTION_READ_ONLY = True",
                    "_preserve_focus_projection()",
                    "status_code=409",
                    "_retired_focus_projection_write()",
                ]
            ),
        )
        commands = "\n".join(f"'{command}'," for command in _QUARANTINED)
        self._write(
            "src/app/commandHandlers/memory.ts",
            "\n".join(
                [
                    "export const NATIVE_FOCUS_LIFECYCLE_OWNERSHIP_VERSION = 'phase20i';",
                    commands,
                    "addNativeFocusContextVerified();",
                    "if (RETIRED_LEGACY_FOCUS_OWNERSHIP_COMMANDS.has(commandMatch.command)) {}",
                    "return handleMemoryCommandCore(commandMatch, deps);",
                ]
            ),
        )
        self._write(
            "backend/app/focus/context.py",
            "def add_focus_context_verified():\n    objectivePreserved = True\n",
        )
        self._write(
            "src/app/lib/semanticFocusLifecycle.ts",
            "const CONTEXT_REASON_PREFIX = 'phase20i-context:';\n",
        )

    def _evaluate(self, context_section: dict[str, object]):
        lifecycle = {
            "startFocus": _health_section(),
            "updateFocus": _health_section(),
            "endFocus": _health_section(),
            "resumeFocus": _health_section(),
        }
        with (
            patch("app.focus.ownership.get_native_focus_lifecycle_health", return_value=lifecycle),
            patch(
                "app.focus.ownership.get_native_focus_summary_health",
                return_value={"saveFocusSummary": _health_section()},
            ),
            patch(
                "app.focus.ownership.get_native_focus_task_health",
                return_value={"linkFocusTasks": _health_section()},
            ),
            patch(
                "app.focus.ownership.get_native_calendar_focus_prep_health",
                return_value={"prepareCalendarFocus": _health_section()},
            ),
            patch(
                "app.focus.ownership.get_native_focus_context_health",
                return_value={"addFocusContext": context_section},
            ),
        ):
            return get_native_focus_ownership_readiness()

    def test_unexercised_context_keeps_ownership_collecting_at_seven_of_eight(self) -> None:
        result = self._evaluate(_health_section(attempts=0))
        self.assertEqual(result.readiness, "collecting")
        self.assertEqual(result.verifiedOperationCount, 7)
        self.assertEqual(result.requiredOperationCount, 8)
        self.assertIn("Run and verify add_focus_context at least once", result.evidenceNeeded)

    def test_verified_context_completes_eight_of_eight_ownership(self) -> None:
        result = self._evaluate(_health_section())
        self.assertEqual(result.readiness, "ready")
        self.assertTrue(result.readyForLegacyProjectionRetirement)
        self.assertEqual(result.verifiedOperationCount, 8)
        self.assertEqual(result.requiredOperationCount, 8)
        self.assertEqual(result.legacyProjection.ownershipVersion, "phase20i")

    def test_latest_context_failure_blocks_readiness(self) -> None:
        result = self._evaluate(_health_section("failed"))
        self.assertEqual(result.readiness, "blocked")
        self.assertFalse(result.readyForLegacyProjectionRetirement)
        self.assertIn(
            "add_focus_context has a degraded latest ownership receipt",
            result.blockers,
        )

    def test_historical_context_failure_does_not_block_newer_verified_receipt(self) -> None:
        section = _health_section()
        section["attemptCount"] = 2
        section["verifiedCount"] = 1
        section["failedCount"] = 1
        result = self._evaluate(section)
        self.assertEqual(result.readiness, "ready")
        operation = next(item for item in result.operations if item.operation == "add_focus_context")
        self.assertEqual(operation.failedCount, 1)
        self.assertEqual(operation.status, "verified")


if __name__ == "__main__":
    unittest.main()
