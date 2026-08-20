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
        self.assertIn("capability !== 'voice' && capability !== 'ui'", source)
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
        self.assertGreaterEqual(source.count("cancelActiveToolContinuation();"), 3)

    def test_app_requests_q_continuation_after_visible_tool_update(self) -> None:
        source = self.app_path.read_text(encoding="utf-8")

        tool_message = source.index(
            "const confirmationMsg = createAssistantMessage(now, confirmationContent, 'tool');"
        )
        post_tool_block_end = source.index(
            "if (compositeStepId) {",
            tool_message,
        )
        post_tool_block = source[tool_message:post_tool_block_end]

        continuation = post_tool_block.index(
            "await continueAfterVerifiedToolUpdate({"
        )

        self.assertGreater(continuation, 0)
        for marker in (
            "userMessage: continuationUserTextForTool",
            "command: commandMatch.command",
            "toolResult: confirmationContent",
            "toolContext: splitCommandResult.continuationContext",
            "recentMessages: messages",
            "activePanel",
        ):
            self.assertIn(marker, post_tool_block)

        self.assertIn(
            "if (!focusTaskReadToolCardIsComplete && !compositeAtomicExecution)",
            post_tool_block,
        )

    def test_confirmed_command_forwards_original_request_to_continuation(self) -> None:
        source = self.app_path.read_text(encoding="utf-8")
        self.assertIn("continuationUserText?: string", source)
        self.assertIn("continuationUserTextForTool", source)

        wrapper_start = source.index(
            "const executeConfirmedPendingCommand = async ("
        )
        wrapper_end = source.index(
            "if (confirmedCalendarEditCommandMatch)",
            wrapper_start,
        )
        wrapper = source[wrapper_start:wrapper_end]

        confirmed_call = wrapper.index("await handleSend(")
        confirmed_end = wrapper.index(");", confirmed_call)
        confirmed_call_source = wrapper[confirmed_call:confirmed_end]

        self.assertIn("commandToRun.frontendCommand", confirmed_call_source)
        self.assertIn("'confirmed'", confirmed_call_source)
        self.assertIn("confirmedCommandMatch", confirmed_call_source)
        self.assertIn("resolvedTaskTargets", confirmed_call_source)
        self.assertIn("commandToRun.originalText", confirmed_call_source)

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
