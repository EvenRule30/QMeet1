from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus import ownership


COMMANDS = [
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


def _health_section(outcome: str = "verified") -> dict[str, object]:
    if outcome == "unexercised":
        return {
            "attemptCount": 0,
            "verifiedCount": 0,
            "failedCount": 0,
            "lastOutcome": "",
            "lastFailureCode": "",
        }
    if outcome == "failed":
        return {
            "attemptCount": 2,
            "verifiedCount": 1,
            "failedCount": 1,
            "lastOutcome": "failed",
            "lastFailureCode": "verification_failed",
        }
    return {
        "attemptCount": 2,
        "verifiedCount": 2,
        "failedCount": 0,
        "lastOutcome": "reused",
        "lastFailureCode": "",
    }


def _write_clean_sources(root: Path) -> None:
    calendar = root / "src/app/hooks/useCalendarController.ts"
    memory_router = root / "backend/app/routers/memory.py"
    wrapper = root / "src/app/commandHandlers/memory.ts"
    context = root / "backend/app/focus/context.py"
    semantic = root / "src/app/lib/semanticFocusLifecycle.ts"

    for path in (calendar, memory_router, wrapper, context, semantic):
        path.parent.mkdir(parents=True, exist_ok=True)

    calendar.write_text(
        "export function useCalendarController() { return {}; }\n",
        encoding="utf-8",
    )
    memory_router.write_text(
        "FOCUS_PROJECTION_READ_ONLY = True\n"
        "def _preserve_focus_projection(): return None, []\n"
        "def _retired_focus_projection_write():\n"
        "    raise HTTPException(status_code=409)\n",
        encoding="utf-8",
    )
    command_literals = "\n".join(f"  '{command}'," for command in COMMANDS)
    wrapper.write_text(
        "export const NATIVE_FOCUS_LIFECYCLE_OWNERSHIP_VERSION = 'phase20i';\n"
        "async function contextPath() { return addNativeFocusContextVerified(request); }\n"
        "const RETIRED_LEGACY_FOCUS_OWNERSHIP_COMMANDS = new Set([\n"
        f"{command_literals}\n"
        "]);\n"
        "if (RETIRED_LEGACY_FOCUS_OWNERSHIP_COMMANDS.has(commandMatch.command)) return blocked;\n"
        "return handleMemoryCommandCore(commandMatch, deps);\n",
        encoding="utf-8",
    )
    context.write_text(
        "def add_focus_context_verified():\n"
        "    return {'objectivePreserved': True}\n",
        encoding="utf-8",
    )
    semantic.write_text(
        "const CONTEXT_REASON_PREFIX = 'phase20i-context:';\n",
        encoding="utf-8",
    )


class FocusOwnershipReadinessPhase20GTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        _write_clean_sources(self.root)
        self.environment = patch.dict(
            os.environ,
            {"QMEET_REPO_ROOT": str(self.root)},
            clear=False,
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp_dir.cleanup()

    def _readiness(self, operation_outcome: str = "verified"):
        section = _health_section(operation_outcome)
        with (
            patch.object(
                ownership,
                "get_native_focus_lifecycle_health",
                return_value={
                    "startFocus": section,
                    "updateFocus": section,
                    "endFocus": section,
                    "resumeFocus": section,
                },
            ),
            patch.object(
                ownership,
                "get_native_focus_summary_health",
                return_value={"saveFocusSummary": section},
            ),
            patch.object(
                ownership,
                "get_native_focus_task_health",
                return_value={"linkFocusTasks": section},
            ),
            patch.object(
                ownership,
                "get_native_calendar_focus_prep_health",
                return_value={"prepareCalendarFocus": section},
            ),
            patch.object(
                ownership,
                "get_native_focus_context_health",
                return_value={"addFocusContext": section},
            ),
        ):
            return ownership.get_native_focus_ownership_readiness()

    def test_ready_is_derived_from_verified_receipts_and_clean_sources(self):
        result = self._readiness()
        self.assertTrue(result.ok)
        self.assertEqual(result.readiness, "ready")
        self.assertTrue(result.readyForLegacyProjectionRetirement)
        self.assertTrue(result.legacyProjection.retired)
        self.assertTrue(result.legacyProjection.fallbackBlocked)
        self.assertEqual(result.legacyProjection.ownershipVersion, "phase20i")
        self.assertEqual(result.legacyProjection.remainingBrowserOwnedWriteSurfaces, [])
        self.assertEqual(result.verifiedOperationCount, 8)
        self.assertEqual(result.requiredOperationCount, 8)

    def test_calendar_browser_writer_blocks_readiness(self):
        calendar = self.root / "src/app/hooks/useCalendarController.ts"
        calendar.write_text(
            "const prepareFocusFromNextCalendarEvent = () => replaceActiveSession(session);\n",
            encoding="utf-8",
        )
        result = self._readiness()
        self.assertFalse(result.ok)
        self.assertEqual(result.readiness, "blocked")
        self.assertFalse(result.legacyProjection.retired)
        self.assertTrue(
            any(
                "calendar hook" in item
                for item in result.legacyProjection.remainingBrowserOwnedWriteSurfaces
            )
        )

    def test_writable_compatibility_memory_projection_blocks_readiness(self):
        memory_router = self.root / "backend/app/routers/memory.py"
        memory_router.write_text(
            "def write(): return **replace_active_session(value)\n",
            encoding="utf-8",
        )
        result = self._readiness()
        self.assertEqual(result.readiness, "blocked")
        self.assertTrue(
            any("compatibility memory router" in item for item in result.blockers)
        )

    def test_missing_fallback_quarantine_blocks_readiness(self):
        wrapper = self.root / "src/app/commandHandlers/memory.ts"
        wrapper.write_text(
            "export const NATIVE_FOCUS_LIFECYCLE_OWNERSHIP_VERSION = 'phase20i';\n"
            "async function contextPath() { return addNativeFocusContextVerified(request); }\n"
            "return handleMemoryCommandCore(commandMatch, deps);\n",
            encoding="utf-8",
        )
        result = self._readiness()
        self.assertEqual(result.readiness, "blocked")
        self.assertFalse(result.legacyProjection.fallbackBlocked)
        self.assertIn(
            "The retired legacy Focus command fallback is not fully blocked",
            result.blockers,
        )

    def test_clean_sources_still_collect_when_receipt_evidence_is_missing(self):
        result = self._readiness("unexercised")
        self.assertTrue(result.ok)
        self.assertEqual(result.readiness, "collecting")
        self.assertFalse(result.readyForLegacyProjectionRetirement)
        self.assertEqual(len(result.evidenceNeeded), 8)
        self.assertIn(
            "Run and verify add_focus_context at least once",
            result.evidenceNeeded,
        )

    def test_failed_receipt_blocks_even_when_sources_are_clean(self):
        result = self._readiness("failed")
        self.assertFalse(result.ok)
        self.assertEqual(result.readiness, "blocked")
        self.assertGreaterEqual(len(result.blockers), 8)


if __name__ == "__main__":
    unittest.main()
