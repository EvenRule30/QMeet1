from pathlib import Path
import re
import unittest


class AgentDeviceUiFrontendPromotionPhase21E4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.app_source = (cls.repo_root / "src" / "app" / "App.tsx").read_text(
            encoding="utf-8"
        )
        cls.promotion_source = (
            cls.repo_root / "src" / "app" / "lib" / "agentDeviceUiPromotion.ts"
        ).read_text(encoding="utf-8")

    def test_frontend_adapter_accepts_only_device_ui_tool_ownership(self) -> None:
        self.assertIn("decision.disposition === 'tool'", self.promotion_source)
        self.assertIn("decision.turnOwner === 'device_ui'", self.promotion_source)
        self.assertIn(
            "decision.proposedCapability === 'device_ui'",
            self.promotion_source,
        )
        self.assertIn(
            "PROMOTED_DEVICE_UI_MIN_CONFIDENCE = 0.9",
            self.promotion_source,
        )
        self.assertIn(
            "Object.keys(proposedArguments).length === 0",
            self.promotion_source,
        )

    def test_frontend_adapter_excludes_session_wide_and_destructive_controls(self) -> None:
        allowlist_match = re.search(
            r"PROMOTED_DEVICE_UI_ACTIONS\s*=\s*\[(.*?)\]\s*as const",
            self.promotion_source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(allowlist_match)
        allowlist = allowlist_match.group(1) if allowlist_match else ""

        for expected in (
            "'go-home'",
            "'open-settings'",
            "'voice-output-on'",
            "'voice-output-off'",
            "'voice-slower'",
            "'stop-speaking'",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, allowlist)

        for excluded in (
            "'clear-chat'",
            "'end-chat'",
            "'cancel-action'",
            "'help'",
            "'identity'",
        ):
            with self.subTest(excluded=excluded):
                self.assertNotIn(excluded, allowlist)

    def test_active_focus_relevance_is_not_a_device_ui_execution_veto(self) -> None:
        resolver_match = re.search(
            r"export function resolvePromotedDeviceUiToolCommand\(.*?\n\}",
            self.promotion_source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(resolver_match)
        resolver = resolver_match.group(0) if resolver_match else ""
        self.assertNotIn("focusRelevant", resolver)

    def test_app_imports_and_resolves_device_ui_promotion(self) -> None:
        self.assertIn("./lib/agentDeviceUiPromotion", self.app_source)
        self.assertIn(
            "isPromotedDeviceUiToolDecision",
            self.app_source,
        )
        self.assertIn(
            "resolvePromotedDeviceUiToolCommand",
            self.app_source,
        )

    def test_device_ui_executes_before_non_focus_owner_fallback(self) -> None:
        branch_index = self.app_source.find(
            "const promotedDeviceUiCandidate ="
        )
        owner_fallback_index = self.app_source.find(
            "const promotedNonFocusToolOwner ="
        )
        self.assertGreaterEqual(branch_index, 0)
        self.assertGreaterEqual(owner_fallback_index, 0)
        self.assertLess(branch_index, owner_fallback_index)

        branch_region = self.app_source[
            branch_index:owner_fallback_index
        ]
        self.assertIn(
            "resolvePromotedDeviceUiToolCommand(promotedSingleIntent)",
            branch_region,
        )
        self.assertIn("'device_ui'", branch_region)
        self.assertIn("'agent'", branch_region)
        self.assertIn("promotedDeviceUiTool.commandMatch", branch_region)
        self.assertIn("return handleSend(", branch_region)

    def test_claimed_but_invalid_device_ui_does_not_reach_legacy_interpreter(self) -> None:
        branch_index = self.app_source.find(
            "const promotedDeviceUiCandidate ="
        )
        owner_fallback_index = self.app_source.find(
            "const promotedNonFocusToolOwner ="
        )
        branch_region = self.app_source[
            branch_index:owner_fallback_index
        ]

        invalid_branch_start = branch_region.find(
            "if (promotedDeviceUiCandidate && !promotedDeviceUiTool)"
        )
        valid_branch_start = branch_region.find(
            "if (promotedDeviceUiTool)",
            invalid_branch_start,
        )

        self.assertGreaterEqual(invalid_branch_start, 0)
        self.assertGreater(valid_branch_start, invalid_branch_start)

        invalid_branch = branch_region[
            invalid_branch_start:valid_branch_start
        ]

        self.assertIn("No control was changed", invalid_branch)
        self.assertIn("return;", invalid_branch)
        self.assertNotIn("/api/command/interpret", invalid_branch)
        self.assertNotIn("interpretCommand", invalid_branch)

    def test_existing_deterministic_device_handlers_remain_execution_authority(self) -> None:
        self.assertIn("handleVoiceCommand(commandMatch", self.app_source)
        self.assertIn("commandMatch.command === 'go-home'", self.app_source)
        self.assertIn("goHome();", self.app_source)


if __name__ == "__main__":
    unittest.main()
