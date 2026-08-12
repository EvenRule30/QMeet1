from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONVERSATION_CLIENT_SOURCE = (
    ROOT / "src" / "app" / "lib" / "conversationLane.ts"
).read_text(encoding="utf-8")


class Phase21BGeneralChatHistoryIsolationTests(unittest.TestCase):
    def test_promoted_general_chat_uses_owner_scoped_history(self):
        self.assertIn(
            "promotedOwner === 'general_chat'",
            CONVERSATION_CLIENT_SOURCE,
        )
        self.assertIn(
            "conversationMessageOwners.get(message.id) === 'general_chat'",
            CONVERSATION_CLIENT_SOURCE,
        )

    def test_focus_conversation_keeps_existing_rich_history(self):
        self.assertIn(
            ": messages;",
            CONVERSATION_CLIENT_SOURCE,
        )

    def test_conversation_messages_are_tagged_when_created(self):
        self.assertIn(
            "rememberConversationMessageOwner(id, owner);",
            CONVERSATION_CLIENT_SOURCE,
        )
        self.assertIn(
            "createUserMessage(visibleUserText, promotedOwner)",
            CONVERSATION_CLIENT_SOURCE,
        )
        self.assertIn(
            "createAssistantMessageId(promotedOwner)",
            CONVERSATION_CLIENT_SOURCE,
        )

    def test_unowned_tool_and_focus_messages_cannot_leak_into_general_history(self):
        self.assertNotIn(
            "message.variant === 'tool' && promotedOwner === 'general_chat'",
            CONVERSATION_CLIENT_SOURCE,
        )
        self.assertIn(
            "messages.filter(",
            CONVERSATION_CLIENT_SOURCE,
        )

    def test_owner_registry_is_bounded(self):
        self.assertIn(
            "CONVERSATION_OWNER_REGISTRY_LIMIT = 240",
            CONVERSATION_CLIENT_SOURCE,
        )
        self.assertIn(
            "conversationMessageOwners.delete(oldestKey);",
            CONVERSATION_CLIENT_SOURCE,
        )

    def test_request_still_carries_promoted_ownership_hint(self):
        self.assertIn(
            "ownershipHint: options.ownershipHint ?? null",
            CONVERSATION_CLIENT_SOURCE,
        )
        self.assertIn(
            "buildRecentConversation(\n      options.recentMessages,\n      options.ownershipHint,",
            CONVERSATION_CLIENT_SOURCE,
        )


if __name__ == "__main__":
    unittest.main()
