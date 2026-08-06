from __future__ import annotations

import re
import unittest
from pathlib import Path


class FocusTerminalSafetyGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.bridge = (root / "src/app/lib/semanticFocusLifecycle.ts").read_text(
            encoding="utf-8"
        )
        cls.app = (root / "src/app/App.tsx").read_text(encoding="utf-8")

    def _function_body(self, name: str) -> str:
        match = re.search(
            rf"(?:export\s+)?function\s+{re.escape(name)}\s*\(.*?\)\s*:\s*[^{{]+\{{(?P<body>.*?)\n\}}",
            self.bridge,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, f"{name} must remain exported by the bridge")
        assert match is not None
        return match.group("body")

    def test_bridge_exposes_direct_terminal_gate(self) -> None:
        helper = self._function_body("getDirectFocusTerminalCommandMatch")
        self.assertIn("terminalDisposition", helper)
        self.assertIn("command: 'end-focus-session'", helper)
        self.assertIn("forceEnd", helper)

    def test_direct_gate_runs_before_exact_command_parsing(self) -> None:
        gate = self.app.index("getDirectFocusTerminalCommandMatch(trimmed)")
        parser = self.app.index("parseCommand(trimmed)")
        self.assertLess(
            gate,
            parser,
            "unambiguous Focus terminal language must be checked before task parsing",
        )

    def test_direct_gate_reenters_verified_command_execution(self) -> None:
        self.assertIn("directFocusTerminalCommandMatch", self.app)
        self.assertIn("'apply verified focus terminal transition'", self.app)
        self.assertIn("directFocusTerminalCommandMatch,", self.app)

    def test_terminal_disposition_covers_completed_and_finished_language(self) -> None:
        body = self._function_body("terminalDisposition")
        self.assertRegex(body, r"complete\|completed")
        self.assertRegex(body, r"finish\|finished")
        self.assertIn("return 'completed';", body)
        self.assertIn("return 'ended';", body)


if __name__ == "__main__":
    unittest.main()
