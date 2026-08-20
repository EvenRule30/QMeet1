from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
OBSERVER = (ROOT / "src" / "app" / "lib" / "agentShadowObserver.ts").read_text(encoding="utf-8")


class AgentFirstSingleIntentOwnershipPhase21BTests(unittest.TestCase):
    def test_terminal_then_parse_inspection_then_explicit_gate_then_agent(self):
        direct_terminal = APP.index("if (directFocusTerminalCommandMatch)")
        parser = APP.index("const parsedCommandMatch =", direct_terminal)
        explicit_gate = APP.index("const explicitDeterministicRoute =", parser)
        agent_first = APP.index("const promotedSingleIntent =", explicit_gate)
        self.assertLess(direct_terminal, parser)
        self.assertLess(parser, explicit_gate)
        self.assertLess(explicit_gate, agent_first)

    def test_exact_parse_is_not_itself_execution_authority(self):
        parser = APP.index("const parsedCommandMatch =")
        explicit_gate = APP.index("const explicitDeterministicRoute =", parser)
        agent_first = APP.index("const promotedSingleIntent =", explicit_gate)
        block = APP[parser:agent_first]
        self.assertIn("resolveExplicitDeterministicRouteBeforeAgent", block)
        self.assertNotIn("if (commandMatch)", block)
        self.assertNotIn("handleMemoryCommand", block)
        self.assertNotIn("handleCalendarCommand", block)

    def test_explicit_command_syntax_skips_agent_wait(self):
        start = APP.index("const observedPromotedSingleIntent =")
        end = APP.index("const promotedSingleIntent =", start)
        block = APP[start:end]
        self.assertIn("!explicitDeterministicRoute", block)
        self.assertIn("resolvePromotedSingleIntentDecision", block)

    def test_promoted_conversation_still_bypasses_legacy_parsers_and_tools(self):
        start = APP.index("if (promotedSingleIntent?.disposition === 'conversation')")
        end = APP.index("const promotedSearchTool =", start)
        block = APP[start:end]
        self.assertIn("await sendNormalChat(", block)
        self.assertIn("return;", block)
        self.assertNotIn("interpretSemanticFocusLifecycle(", block)
        self.assertNotIn("interpretCommandIntent(", block)
        self.assertNotIn("handleSend(", block)

    def test_explicit_focus_field_assignment_forces_verified_semantic_preflight(self):
        start = APP.index("const semanticLifecyclePreflightBeforeCommandRouting =")
        end = APP.index("const deferredSemanticFocusLifecycleMessage =", start)
        block = APP[start:end]
        self.assertIn("explicitDeterministicRoute?.kind === 'focus-mutation'", block)
        self.assertIn("await interpretSemanticFocusLifecycle(trimmed)", block)

    def test_bare_aliases_are_not_declared_explicit_commands(self):
        start = OBSERVER.index("export function resolveExplicitDeterministicRouteBeforeAgent")
        end = OBSERVER.index("export type PromotedSingleIntentDecision", start)
        block = OBSERVER[start:end]
        self.assertIn("EXPLICIT_COMMAND_LEAD.test(text)", block)
        self.assertIn("EXPLICIT_FOCUS_FIELD_ASSIGNMENT.test(text)", block)
        self.assertNotIn("text === 'health'", block)
        self.assertNotIn("text === 'status'", block)

    def test_pending_confirmation_safety_still_preempts_agent_first_routing(self):
        pending = APP.index("if (pendingInterpreterCommand)")
        agent_first = APP.index("const promotedSingleIntent =")
        self.assertLess(pending, agent_first)
        self.assertIn("isConfirmingPendingCommand(trimmed)", APP[pending:agent_first])
        self.assertIn("isRejectingPendingCommand(trimmed)", APP[pending:agent_first])

    def test_only_search_tool_is_promoted_to_execution_in_this_slice(self):
        start = APP.index("const promotedSearchTool =")
        end = APP.index("const promotedNonFocusToolOwner =", start)
        block = APP[start:end]
        self.assertIn("resolvePromotedSearchToolCommand", block)
        self.assertIn("promotedSearchTool.commandMatch", block)
        self.assertIn("'agent'", block)
        self.assertNotIn("promotedSingleIntent.proposedArguments", block)
        self.assertNotIn("handleCalendarCommand", block)
        self.assertNotIn("handleMemoryCommand", block)
        self.assertNotIn("handleNotesCommand", block)

    def test_other_non_focus_tool_owners_remain_advisory(self):
        start = APP.index("const promotedNonFocusToolOwner =")
        end = APP.index("const naturalTaskCompletionEligible =", start)
        block = APP[start:end]
        self.assertIn("promotedSingleIntent.turnOwner !== 'focus'", block)
        self.assertNotIn("proposedArguments", block)
        self.assertNotIn("handleSend(", block)

    def test_ambiguous_single_intent_wait_is_bounded(self):
        self.assertIn("AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 7000", OBSERVER)
        start = OBSERVER.index("export async function resolvePromotedSingleIntentDecision")
        end = OBSERVER.index("export type AgentShadowFocusMutationGuardResult", start)
        block = OBSERVER[start:end]
        self.assertIn("Promise.race", block)
        self.assertIn("Existing deterministic routing remains authoritative", block)


if __name__ == "__main__":
    unittest.main()
