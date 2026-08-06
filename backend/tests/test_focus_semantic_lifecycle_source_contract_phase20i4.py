from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "app" / "lib" / "semanticFocusLifecycle.ts"


class SemanticFocusLifecycleSourceContractPhase20I4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_terminal_detector_keeps_historical_exact_return(self) -> None:
        match = re.search(
            r"function looksLikeFocusTerminalLanguage\(message: string\): boolean \{(?P<body>.*?)\n\}",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        detector = match.group("body")
        self.assertIn("const directFocusTerminalPattern", detector)
        self.assertIn("const focusTarget", detector)
        self.assertIn("const terminalLanguage", detector)
        self.assertIn("return directFocusTerminalPattern.test(text);", detector)

    def test_direct_terminal_helper_keeps_extractable_signature(self) -> None:
        match = re.search(
            r"export function shouldRouteDirectFocusTerminalLanguageBeforeSemanticPreflight\(message: string\): boolean \{(?P<body>.*?)\n\}",
            self.source,
            re.DOTALL,
        )
        self.assertIsNotNone(match)
        self.assertIn(
            "return looksLikeFocusTerminalLanguage(message);",
            match.group("body"),
        )


if __name__ == "__main__":
    unittest.main()
