from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESOLVER = ROOT / "src" / "app" / "lib" / "taskCompletionResolver.ts"


class TaskCompletionResolverPhase21C5Tests(unittest.TestCase):
    def test_partial_reference_matching_is_explicit_and_ambiguity_safe(self):
        source = RESOLVER.read_text(encoding="utf-8")

        self.assertIn("function containsAllQueryTokens(", source)
        self.assertIn(
            "const contained = candidates.filter((task) =>",
            source,
        )
        self.assertIn(
            "if (contained.length === 1)",
            source,
        )
        self.assertIn(
            "return { kind: 'likely', task: contained[0] };",
            source,
        )
        self.assertIn(
            "if (contained.length > 1)",
            source,
        )
        self.assertIn(
            "kind: 'ambiguous'",
            source,
        )

    def test_invoice_and_presentation_examples_are_documented_at_the_runtime_seam(self):
        source = RESOLVER.read_text(encoding="utf-8")

        self.assertIn(
            '"invoice" -> "sending invoice"',
            source,
        )
        self.assertIn(
            '"presentation outline" -> "review presentation outline"',
            source,
        )

    def test_existing_natural_completion_path_stays_in_place(self):
        source = RESOLVER.read_text(encoding="utf-8")

        self.assertIn(
            "export function resolveGlobalTaskCompletionReference(",
            source,
        )
        self.assertIn(
            "export function resolveNaturalGlobalTaskCompletionRequest(",
            source,
        )
        self.assertIn(
            "const resolution = resolveGlobalTaskCompletionReference(query, tasks);",
            source,
        )


if __name__ == "__main__":
    unittest.main()
