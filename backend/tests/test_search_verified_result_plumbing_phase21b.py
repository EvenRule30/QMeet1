from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class SearchVerifiedResultPlumbingPhase21BTests(unittest.TestCase):
    def _read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_search_handler_builds_context_from_actual_response(self) -> None:
        source = self._read("src/app/commandHandlers/search.ts")

        self.assertIn("continuationContext?: string;", source)
        self.assertIn("buildVerifiedSearchContinuationContext", source)
        self.assertIn("if (!searchResponse.ok) return '';", source)
        self.assertIn("searchResponse.query", source)
        self.assertIn("searchResponse.summary", source)
        self.assertIn("searchResponse.recommendation", source)
        self.assertIn("searchResponse.steps", source)
        self.assertIn("searchResponse.sources", source)
        self.assertIn("qmeetSearchResultVerified: true", source)
        self.assertIn(
            "buildVerifiedSearchContinuationContext(searchResponse)",
            source,
        )
        self.assertIn(
            "...(continuationContext ? { continuationContext } : {})",
            source,
        )

    def test_failed_search_does_not_fabricate_verified_context(self) -> None:
        source = self._read("src/app/commandHandlers/search.ts")

        success_start = source.index("if (searchResponse?.ok) {")
        continuation_call = source.index(
            "buildVerifiedSearchContinuationContext(searchResponse)",
            success_start,
        )
        binding_call = source.index(
            "buildVerifiedSearchResultText(searchResponse)",
            continuation_call,
        )
        failure_assignment = source.index(
            "confirmationContent =\n"
            "            searchResponse?.message ||",
            binding_call,
        )
        result_return = source.index(
            "return {\n"
            "        handled: true,\n"
            "        confirmationContent,",
            failure_assignment,
        )

        # Both verified outputs are produced inside the successful response path
        # and before the real failed-search branch.
        self.assertLess(continuation_call, failure_assignment)
        self.assertLess(binding_call, failure_assignment)

        # The actual failed-search branch must not create either verified value.
        failure_block = source[failure_assignment:result_return]
        self.assertNotIn(
            "buildVerifiedSearchContinuationContext(",
            failure_block,
        )
        self.assertNotIn(
            "buildVerifiedSearchResultText(",
            failure_block,
        )
        self.assertNotIn(
            "compositeBindings = {",
            failure_block,
        )

    def test_app_passes_verified_search_context_to_tool_continuation(self) -> None:
        source = self._read("src/app/App.tsx")

        self.assertIn(
            "toolContext: splitCommandResult.continuationContext",
            source,
        )

    def test_g2c_binding_and_normal_continuation_share_actual_search_response(self) -> None:
        source = self._read("src/app/commandHandlers/search.ts")

        self.assertIn(
            "buildVerifiedSearchResultText(searchResponse)",
            source,
        )
        self.assertIn(
            "buildVerifiedSearchContinuationContext(searchResponse)",
            source,
        )
        self.assertIn("compositeBindings = {", source)
        self.assertIn("searchResultText", source)


if __name__ == "__main__":
    unittest.main()
