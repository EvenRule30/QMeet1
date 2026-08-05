from __future__ import annotations

from pathlib import Path
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
        quarantine = self.source.index(
            "if (RETIRED_LEGACY_FOCUS_LIFECYCLE_COMMANDS.has(commandMatch.command))"
        )
        fallback = self.source.rindex(
            "return handleMemoryCommandCore(commandMatch, deps);"
        )
        self.assertLess(quarantine, fallback)

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
