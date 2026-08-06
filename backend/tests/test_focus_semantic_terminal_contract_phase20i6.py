from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "app" / "lib" / "semanticFocusLifecycle.ts"


class SemanticFocusTerminalContractPhase20I6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_detector_preserves_every_historical_safety_marker(self) -> None:
        match = re.search(
            r"function looksLikeFocusTerminalLanguage\(message: string\): boolean \{(?P<body>.*?)\n\}",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn(r"focus(?:\s+session)?|session|work", body)
        self.assertRegex(body, r"finish\|finished")
        self.assertIn("focusTarget && terminalLanguage", body)
        self.assertIn("focusReference && terminalLanguage", body)
        self.assertIn("return directFocusTerminalPattern.test(text);", body)

    def test_direct_gate_exports_keep_extractable_one_line_signatures(self) -> None:
        names = (
            "shouldRouteDirectFocusTerminalLanguageBeforeSemanticPreflight",
            "shouldRouteDirectFocusTerminalLanguageBeforeCommandRouting",
            "shouldRouteDirectFocusTerminalBeforeSemanticPreflight",
            "shouldRouteDirectFocusTerminalBeforeCommandRouting",
            "shouldRouteDirectFocusTerminalLanguageBeforeCommandParsing",
            "shouldRouteDirectFocusTerminalBeforeCommandParsing",
            "shouldRouteDirectFocusTerminalLanguageBeforeInterpreter",
            "shouldRouteDirectFocusTerminalBeforeInterpreter",
        )
        for name in names:
            with self.subTest(name=name):
                match = re.search(
                    rf"export function {name}\(message: string\): boolean \{{(?P<body>.*?)\n\}}",
                    self.source,
                    re.DOTALL,
                )
                self.assertIsNotNone(match)
                self.assertIn(
                    "return looksLikeFocusTerminalLanguage(message);",
                    match.group("body"),
                )

    def test_direct_command_match_helper_keeps_extractable_signature(self) -> None:
        match = re.search(
            r"export function getDirectFocusTerminalCommandMatch\(message: string\): CommandMatch \| null \{(?P<body>.*?)\n\}",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        body = match.group("body")
        self.assertIn("const disposition = terminalDisposition(message);", body)
        self.assertIn("command: 'end-focus-session'", body)


if __name__ == "__main__":
    unittest.main()
