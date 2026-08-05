from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
MEMORY_WRAPPER = ROOT / "src" / "app" / "commandHandlers" / "memory.ts"
APP_ROOT = ROOT / "src" / "app"


class FocusLegacyLifecycleQuarantinePhase20E1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = MEMORY_WRAPPER.read_text(encoding="utf-8")

    def test_native_lifecycle_ownership_version_is_declared(self) -> None:
        self.assertIn(
            "NATIVE_FOCUS_LIFECYCLE_OWNERSHIP_VERSION = 'phase20e1'",
            self.source,
        )

    def test_all_legacy_lifecycle_commands_are_quarantined(self) -> None:
        for command in (
            "start-focus-session",
            "update-focus-session",
            "resume-last-focus-session",
            "end-focus-session",
            "end-focus-with-summary",
            "wrap-up-meeting-focus",
        ):
            self.assertIn(f"'{command}'", self.source)

    def test_quarantine_runs_before_memory_core_fallback(self) -> None:
        quarantine_match = re.search(
            r"if\s*\(\s*"
            r"RETIRED_LEGACY_FOCUS_LIFECYCLE_COMMANDS\s*\.\s*has\s*\(\s*"
            r"commandMatch\s*\.\s*command\s*,?\s*"
            r"\)\s*\)",
            self.source,
        )
        self.assertIsNotNone(
            quarantine_match,
            "memory.ts must quarantine RETIRED_LEGACY_FOCUS_LIFECYCLE_COMMANDS "
            "before calling memoryCore; line wrapping and Prettier formatting are allowed.",
        )

        fallback_calls = list(
            re.finditer(
                r"\bhandleMemoryCommandCore\s*\(\s*commandMatch\s*,\s*deps\s*,?\s*\)",
                self.source,
            )
        )
        self.assertTrue(
            fallback_calls,
            "memory.ts must retain a fallback call to "
            "handleMemoryCommandCore(commandMatch, deps).",
        )
        self.assertLess(quarantine_match.start(), fallback_calls[-1].start())

    def test_quarantine_failure_wording_cannot_claim_success(self) -> None:
        self.assertIn("No Focus change was made.", self.source)
        self.assertIn("I blocked a retired legacy Focus lifecycle path", self.source)

    def test_meeting_wrap_up_is_not_allowed_to_end_via_legacy_core(self) -> None:
        self.assertIn("command === 'wrap-up-meeting-focus'", self.source)
        self.assertIn("without one verified transaction", self.source)
        self.assertIn("complete the Focus as separate verified actions", self.source)

    def test_production_code_does_not_import_memory_core_directly(self) -> None:
        offenders: list[str] = []
        for path in APP_ROOT.rglob("*.ts*"):
            if path in {MEMORY_WRAPPER, APP_ROOT / "commandHandlers" / "memoryCore.ts"}:
                continue
            source = path.read_text(encoding="utf-8")
            if "memoryCore" in source:
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
