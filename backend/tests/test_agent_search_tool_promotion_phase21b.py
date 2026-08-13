from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "app" / "App.tsx"
OBSERVER = ROOT / "src" / "app" / "lib" / "agentShadowObserver.ts"
PROMOTION = ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
CHAT_FLOW = ROOT / "src" / "app" / "lib" / "chatFlowUtils.ts"
SEARCH_HANDLER = ROOT / "src" / "app" / "commandHandlers" / "search.ts"


class AgentSearchToolPromotionPhase21BTests(unittest.TestCase):
    def test_promoted_decision_preserves_proposed_arguments(self) -> None:
        source = OBSERVER.read_text(encoding="utf-8")
        self.assertIn("proposedArguments: Record<string, unknown>;", source)
        self.assertGreaterEqual(
            source.count("proposedArguments: { ...decision.proposedArguments },"),
            3,
        )

    def test_search_promotion_is_narrow_and_argument_validated(self) -> None:
        source = PROMOTION.read_text(encoding="utf-8")
        self.assertIn("decision.turnOwner !== 'search'", source)
        self.assertIn("decision.proposedCapability !== 'search'", source)
        self.assertIn("decision.proposedAction !== 'run-search'", source)
        self.assertIn("keys.length !== 1 || keys[0] !== 'query'", source)
        self.assertIn("typeof rawQuery !== 'string'", source)
        self.assertIn("MAX_PROMOTED_SEARCH_QUERY_LENGTH = 500", source)
        self.assertIn("command: 'run-search'", source)
        self.assertIn("payload: query", source)
        self.assertNotIn("runWebSearch", source)

    def test_app_promotes_search_before_generic_tool_owner_fallback(self) -> None:
        source = APP.read_text(encoding="utf-8")
        search_index = source.index("const promotedSearchTool = resolvePromotedSearchToolCommand")
        fallback_index = source.index("const promotedNonFocusToolOwner =")
        self.assertLess(search_index, fallback_index)
        self.assertIn("'Agent-promoted Search tool'", source)
        self.assertRegex(
            source,
            re.compile(
                r"return handleSend\(\s*promotedSearchTool\.query,\s*"
                r"visibleUserText,\s*'agent',\s*"
                r"promotedSearchTool\.commandMatch,\s*\[\],\s*visibleUserText,\s*\);",
                re.DOTALL,
            ),
        )

    def test_agent_route_is_distinct_from_fuzzy_interpreter(self) -> None:
        source = CHAT_FLOW.read_text(encoding="utf-8")
        self.assertIn("'confirmed' | 'agent'", source)
        self.assertIn(
            "if (commandRoute === 'agent') return 'Agent-promoted tool command';",
            source,
        )

    def test_explicit_deterministic_commands_still_skip_agent_promotion(self) -> None:
        source = APP.read_text(encoding="utf-8")
        explicit_index = source.index("const explicitDeterministicRoute =")
        promoted_index = source.index("const promotedSingleIntent =")
        self.assertLess(explicit_index, promoted_index)
        promoted_block = source[promoted_index:source.index("if (promotedSingleIntent?.disposition === 'conversation')")]
        self.assertIn("!explicitDeterministicRoute", promoted_block)

    def test_existing_search_handler_remains_executor(self) -> None:
        source = SEARCH_HANDLER.read_text(encoding="utf-8")
        self.assertIn("case 'run-search'", source)
        self.assertIn("commandMatch.payload?.trim()", source)
        self.assertIn("await deps.runWebSearch(preparedSearchQuery)", source)
        self.assertIn("deps.setActivePanel('search')", source)


if __name__ == "__main__":
    unittest.main()
