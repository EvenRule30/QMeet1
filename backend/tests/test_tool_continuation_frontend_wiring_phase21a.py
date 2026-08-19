from __future__ import annotations

import unittest
from pathlib import Path


class ToolContinuationFrontendPhase21ATests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[2]
        self.app_path = self.root / "src/app/App.tsx"
        self.client_path = self.root / "src/app/lib/toolContinuation.ts"

    def test_client_targets_read_only_phase21a_continuation_route(self) -> None:
        source = self.client_path.read_text(encoding="utf-8")
        self.assertIn("/api/chat/tool-continuation/stream", source)
        self.assertIn("verified: true", source)
        self.assertIn("success: true", source)
        self.assertIn("frontend-deterministic-command", source)

    def test_client_keeps_ui_and_voice_commands_silent(self) -> None:
        source = self.client_path.read_text(encoding="utf-8")
        self.assertIn(
            "capability !== 'voice' && capability !== 'ui'",
            source,
        )
        self.assertIn("const VOICE_COMMANDS", source)
        self.assertIn("const UI_COMMANDS", source)

    def test_client_maps_global_capability_categories_before_continuation(self) -> None:
        source = self.client_path.read_text(encoding="utf-8")
        for marker in (
            "const FOCUS_COMMANDS",
            "const CALENDAR_COMMANDS",
            "const SEARCH_COMMANDS",
            "const NOTES_COMMANDS",
            "const TASK_COMMANDS",
            "const MEMORY_COMMANDS",
            "const VISUAL_COMMANDS",
        ):
            self.assertIn(marker, source)

    def test_client_is_fail_soft_after_verified_tool_result(self) -> None:
        source = self.client_path.read_text(encoding="utf-8")
        self.assertIn(
            "preserving the verified tool result without retrying the tool",
            source,
        )
        self.assertNotIn("variant: 'error'", source)

    def test_app_cancels_stale_continuation_on_new_turn_and_shutdown(self) -> None:
        source = self.app_path.read_text(encoding="utf-8")
        self.assertIn("cancelActiveToolContinuation", source)
        self.assertGreaterEqual(
            source.count("cancelActiveToolContinuation();"),
            3,
        )

    def test_app_requests_q_continuation_after_visible_tool_update(self) -> None:
        source = self.app_path.read_text(encoding="utf-8")

        # Anchor the continuation search after the generic visible tool card.
        # Phase 21D1 adds another valid continuation earlier in App.tsx for
        # verified targeted task deletion, so a file-global first occurrence is
        # no longer the continuation associated with this tool card.
        tool_message = source.index(
            "createAssistantMessage(now, confirmationContent, 'tool')"
        )
        continuation = source.index(
            "await continueAfterVerifiedToolUpdate({",
            tool_message,
        )
        final_return = source.index("      return;", continuation)

        self.assertLess(tool_message, continuation)
        self.assertLess(continuation, final_return)
        for marker in (
            "userMessage: continuationUserTextForTool",
            "command: commandMatch.command",
            "toolResult: confirmationContent",
            "recentMessages: messages",
            "activePanel",
        ):
            self.assertIn(marker, source[continuation:final_return])

    def test_targeted_task_delete_continuation_follows_its_visible_tool_update(self) -> None:
        source = self.app_path.read_text(encoding="utf-8")

        delete_receipt = source.index(
            "const confirmationContent = `Deleted task:"
        )
        tool_message = source.index(
            "const confirmationMsg = createAssistantMessage(",
            delete_receipt,
        )
        continuation = source.index(
            "await continueAfterVerifiedToolUpdate({",
            tool_message,
        )
        final_return = source.index("              return;", continuation)

        self.assertLess(delete_receipt, tool_message)
        self.assertLess(tool_message, continuation)
        self.assertLess(continuation, final_return)

        continuation_source = source[continuation:final_return]
        self.assertIn(
            "userMessage: commandToRun.originalText",
            continuation_source,
        )
        self.assertIn(
            "qmeetTaskDeleteMode=targeted",
            continuation_source,
        )
        self.assertIn(
            "toolResult: confirmationContent",
            continuation_source,
        )

    def test_confirmed_command_forwards_original_request_to_continuation(self) -> None:
        source = self.app_path.read_text(encoding="utf-8")
        self.assertIn("continuationUserText?: string", source)
        self.assertIn("continuationUserTextForTool", source)
        confirmed_call = source.index(
            "return handleSend(\n              commandToRun.frontendCommand"
        )
        confirmed_end = source.index("            );", confirmed_call)
        self.assertIn(
            "commandToRun.originalText",
            source[confirmed_call:confirmed_end],
        )

    def test_client_suppresses_failed_receipts_and_navigation_chatter(self) -> None:
        source = self.client_path.read_text(encoding="utf-8")
        self.assertIn("hasFailureLanguage(toolResult)", source)
        for command in (
            "'open-calendar'",
            "'open-search'",
            "'open-notes'",
            "'go-home'",
            "'voice-output-on'",
        ):
            self.assertIn(command, source)

    def test_handle_send_tracks_recent_messages_for_continuation_context(self) -> None:
        source = self.app_path.read_text(encoding="utf-8")
        self.assertIn(
            "googleCalendarEvents, messages, sendNormalChat]);",
            source,
        )


if __name__ == "__main__":
    unittest.main()
