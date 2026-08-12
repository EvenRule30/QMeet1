from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
OBSERVER = (ROOT / "src" / "app" / "lib" / "agentShadowObserver.ts").read_text(encoding="utf-8")


class ExplicitCommandPrecedencePhase21BTests(unittest.TestCase):
    def test_resolver_is_wired_before_agent_promotion(self):
        parser = APP.index("const parsedCommandMatch =")
        resolver = APP.index("resolveExplicitDeterministicRouteBeforeAgent", parser)
        agent = APP.index("const promotedSingleIntent =", resolver)
        self.assertLess(parser, resolver)
        self.assertLess(resolver, agent)

    def test_explicit_route_prevents_agent_promotion(self):
        start = APP.index("const promotedSingleIntent =")
        end = APP.index("if (promotedSingleIntent?.disposition === 'conversation')", start)
        self.assertIn("!explicitDeterministicRoute", APP[start:end])

    def test_explicit_action_verbs_cover_status_menu_search_and_mutations(self):
        lead_start = OBSERVER.index("const EXPLICIT_COMMAND_LEAD")
        lead_end = OBSERVER.index(";", lead_start)
        lead = OBSERVER[lead_start:lead_end]
        for verb in ("open", "show", "search", "add", "change", "update", "start", "rename", "set"):
            self.assertIn(verb, lead)

    def test_focus_colon_assignment_has_dedicated_explicit_route(self):
        self.assertIn("EXPLICIT_FOCUS_FIELD_ASSIGNMENT", OBSERVER)
        self.assertIn("kind: 'focus-mutation'", OBSERVER)
        self.assertIn("explicitDeterministicRoute?.kind === 'focus-mutation'", APP)

    def test_bare_alias_can_still_reach_agent(self):
        # The parser is inspected first, but the model is skipped only when the
        # explicit resolver returns a route. This preserves context-sensitive
        # handling for aliases like `health` while keeping `show status` exact.
        start = APP.index("const explicitDeterministicRoute =")
        end = APP.index("if (promotedSingleIntent?.disposition === 'conversation')", start)
        block = APP[start:end]
        self.assertIn("!explicitDeterministicRoute", block)
        self.assertIn("resolvePromotedSingleIntentDecision", block)


if __name__ == "__main__":
    unittest.main()
