from __future__ import annotations

import re
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


class NativeFocusEndInstallContractPhase20D2B1Tests(unittest.TestCase):
    def test_backend_exposes_verified_terminal_executor_and_route(self) -> None:
        lifecycle = (BACKEND_ROOT / "app/focus/lifecycle.py").read_text(
            encoding="utf-8"
        )
        router = (BACKEND_ROOT / "app/routers/focus_lifecycle.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("class NativeFocusEndRequest", lifecycle)
        self.assertIn("class NativeFocusEndResult", lifecycle)
        self.assertIn("def end_focus_verified", lifecycle)
        self.assertIn("FocusEventType.FOCUS_ENDED", lifecycle)
        self.assertIn("FocusEventType.FOCUS_COMPLETED", lifecycle)
        self.assertIn('"endFocus"', lifecycle)
        self.assertIn('@router.post("/end", response_model=NativeFocusEndResult)', router)
        self.assertIn("end_focus_verified(request)", router)
        self.assertIn('"successClaimAllowed": False', router)

    def test_frontend_requires_terminal_proof_before_clearing_projection(self) -> None:
        lifecycle_client = (
            REPO_ROOT / "src/app/lib/nativeFocusLifecycle.ts"
        ).read_text(encoding="utf-8")
        memory = (REPO_ROOT / "src/app/commandHandlers/memory.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("export async function endNativeFocusVerified", lifecycle_client)
        self.assertIn("/api/focus/lifecycle/end", lifecycle_client)
        self.assertIn("isVerifiedNativeFocusEndResult", lifecycle_client)
        self.assertIn("verification.noFocusOpen === true", lifecycle_client)
        self.assertIn("verification.terminalEventPersisted === true", lifecycle_client)
        self.assertIn("applyVerifiedFocusProjection(null)", memory)

        await_index = memory.index("const result = await endNativeFocusVerified")
        clear_index = memory.index("applyVerifiedFocusProjection(null)", await_index)
        failure_index = memory.index("} catch (error) {", clear_index)
        self.assertLess(await_index, clear_index)
        self.assertLess(clear_index, failure_index)

    def test_summary_guard_remains_before_native_terminal_execution(self) -> None:
        memory = (REPO_ROOT / "src/app/commandHandlers/memory.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("shouldGuardNativeFocusEnd(activeSession)", memory)
        self.assertIn("hasSavedFocusSummary", memory)
        self.assertIn("end Focus anyway", memory)
        self.assertIn("commandMatch.command === 'end-focus-with-summary'", memory)
        self.assertIn("separate verified receipts", memory)

        guard_index = memory.index("shouldGuardNativeFocusEnd(activeSession)")
        execute_index = memory.index("await endNativeFocusVerified", guard_index)
        self.assertLess(guard_index, execute_index)

    def test_semantic_contract_includes_end_complete_and_summary_block(self) -> None:
        backend = (
            BACKEND_ROOT / "app/focus/semantic_lifecycle_preflight.py"
        ).read_text(encoding="utf-8")
        frontend = (
            REPO_ROOT / "src/app/lib/semanticFocusLifecycle.ts"
        ).read_text(encoding="utf-8")
        app = (REPO_ROOT / "src/app/App.tsx").read_text(encoding="utf-8")

        self.assertIn('END = "end"', backend)
        self.assertIn('COMPLETE = "complete"', backend)
        self.assertIn("_explicit_summary_end_request", backend)
        self.assertIn("summary_end_requires_separate_verified_receipt", backend)
        self.assertIn("payload.intent === 'end'", frontend)
        self.assertIn("payload.intent === 'complete'", frontend)
        self.assertIn("command: 'end-focus-session'", frontend)
        self.assertIn("commandMatch?.command === 'end-focus-session'", frontend)
        self.assertIn("commandMatch?.command === 'end-focus-with-summary'", frontend)
        self.assertIn("semanticFocusLifecycle.kind === 'end'", app)
        self.assertIn("semanticFocusLifecycle.kind === 'complete'", app)

    def test_frontend_and_backend_bridge_versions_match(self) -> None:
        backend = (
            BACKEND_ROOT / "app/focus/semantic_lifecycle_preflight.py"
        ).read_text(encoding="utf-8")
        frontend = (
            REPO_ROOT / "src/app/lib/semanticFocusLifecycle.ts"
        ).read_text(encoding="utf-8")

        backend_match = re.search(
            r'SEMANTIC_LIFECYCLE_BRIDGE_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]',
            backend,
        )
        frontend_match = re.search(
            r'SEMANTIC_FOCUS_LIFECYCLE_BRIDGE_VERSION\s*=\s*[\'"]([^\'"]+)[\'"]',
            frontend,
        )
        self.assertIsNotNone(backend_match)
        self.assertIsNotNone(frontend_match)
        assert backend_match is not None
        assert frontend_match is not None
        self.assertEqual(backend_match.group(1), frontend_match.group(1))
        self.assertEqual(backend_match.group(1), "phase20d2b1")


if __name__ == "__main__":
    unittest.main()
