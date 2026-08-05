from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]
MEMORY_WRAPPER = ROOT / "src" / "app" / "commandHandlers" / "memory.ts"
APP_ROOT = ROOT / "src" / "app"

QUARANTINE_GUARD_PATTERN = re.compile(
    r"if\s*\(\s*"
    r"(?P<set_name>RETIRED_LEGACY_FOCUS_[A-Z_]*COMMANDS)"
    r"\s*\.\s*has\s*\(\s*"
    r"commandMatch\s*\.\s*command\s*,?\s*"
    r"\)\s*\)"
)


class FocusLegacyLifecycleQuarantinePhase20E1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = MEMORY_WRAPPER.read_text(encoding="utf-8")

    def _quarantine_guard(self) -> re.Match[str]:
        match = QUARANTINE_GUARD_PATTERN.search(self.source)
        self.assertIsNotNone(
            match,
            "memory.ts must guard retired legacy Focus ownership commands "
            "before calling memoryCore; identifier changes, line wrapping, and "
            "Prettier formatting are allowed.",
        )
        assert match is not None
        return match

    def _quarantine_set_body(self) -> str:
        guard = self._quarantine_guard()
        set_name = guard.group("set_name")
        declaration = re.search(
            rf"const\s+{re.escape(set_name)}\s*=\s*"
            r"new\s+Set(?:\s*<[^>]+>)?\s*"
            r"\(\s*\[\s*(?P<body>.*?)\s*\]\s*\)\s*;",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(
            declaration,
            f"memory.ts must declare {set_name} as the Set used by the "
            "retired-command quarantine guard.",
        )
        assert declaration is not None
        return declaration.group("body")

    def test_native_lifecycle_ownership_version_is_declared(self) -> None:
        self.assertIn(
            "NATIVE_FOCUS_LIFECYCLE_OWNERSHIP_VERSION = 'phase20e1'",
            self.source,
        )

    def test_all_legacy_lifecycle_commands_are_quarantined(self) -> None:
        quarantine_set_body = self._quarantine_set_body()
        for command in (
            "start-focus-session",
            "update-focus-session",
            "resume-last-focus-session",
            "end-focus-session",
            "end-focus-with-summary",
            "wrap-up-meeting-focus",
        ):
            self.assertIn(
                f"'{command}'",
                quarantine_set_body,
                f"{command} must remain in the Set used by the retired legacy "
                "Focus quarantine guard.",
            )

    def test_quarantine_runs_before_memory_core_fallback(self) -> None:
        quarantine = self._quarantine_guard()
        fallback_calls = list(
            re.finditer(
                r"\breturn\s+(?:await\s+)?handleMemoryCommandCore\s*"
                r"\(\s*commandMatch\s*,\s*deps\s*,?\s*\)\s*;",
                self.source,
            )
        )
        self.assertTrue(
            fallback_calls,
            "memory.ts must retain a final fallback return to "
            "handleMemoryCommandCore(commandMatch, deps).",
        )
        self.assertLess(
            quarantine.start(),
            fallback_calls[-1].start(),
            "The retired legacy Focus quarantine must execute before the final "
            "memoryCore fallback.",
        )

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
