from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus import legacy
from app.focus.canonical_work_context_source import (
    get_canonical_active_session,
    install_canonical_work_context_source,
)
from app.focus.models import FocusState, FocusStatus


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_SOURCE = REPO_ROOT / "backend" / "app" / "main.py"
PLANNER_SOURCE = REPO_ROOT / "backend" / "app" / "focus" / "planner.py"
WORK_CONTEXT_SOURCE = REPO_ROOT / "backend" / "app" / "work_context.py"


class FocusCanonicalResurrectionGuardPhase20VTests(unittest.TestCase):
    def test_legacy_runtime_bootstrap_is_disabled_by_default(self) -> None:
        stale_session = {
            "activeSession": {
                "id": "legacy-meeting",
                "title": "Prepare for meeting",
                "mode": "meeting",
                "goal": "Prepare for meeting",
            }
        }
        stale_context = {
            "activeContext": {
                "title": "Prepare for meeting",
                "objective": "Prepare for meeting",
                "constraints": ["Keep the total cost under $1,000"],
                "stage": "planning",
            }
        }

        with (
            patch.dict(os.environ, {}, clear=False),
            patch.object(
                legacy,
                "_call_optional",
                side_effect=[stale_session, stale_context],
            ) as optional_call,
        ):
            os.environ.pop(legacy.LEGACY_FOCUS_BOOTSTRAP_ENV, None)
            seed = legacy.load_legacy_focus_seed()

        self.assertIsNone(seed)
        optional_call.assert_not_called()

    def test_legacy_import_remains_explicitly_opt_in_for_migration(self) -> None:
        stale_session = {
            "activeSession": {
                "id": "legacy-meeting",
                "title": "Prepare for meeting",
                "mode": "meeting",
                "goal": "Prepare for meeting",
                "startedAt": "2026-08-01T12:00:00-07:00",
            }
        }
        stale_context = {
            "activeContext": {
                "title": "Prepare for meeting",
                "objective": "Prepare for meeting",
                "constraints": ["Keep the total cost under $1,000"],
                "stage": "planning",
                "updatedAt": "2026-08-01T12:01:00-07:00",
            }
        }

        with (
            patch.dict(
                os.environ,
                {legacy.LEGACY_FOCUS_BOOTSTRAP_ENV: "1"},
                clear=False,
            ),
            patch.object(
                legacy,
                "_call_optional",
                side_effect=[stale_session, stale_context],
            ),
        ):
            seed = legacy.load_legacy_focus_seed()

        self.assertIsNotNone(seed)
        assert seed is not None
        self.assertEqual(seed.focusId, "legacy-meeting")
        self.assertIn("Keep the total cost under $1,000", seed.constraints)

    def test_canonical_adapter_exposes_only_open_focus_states(self) -> None:
        active_state = FocusState(
            focusId="focus-new",
            title="prepare a short project update",
            objective="summarize progress and next steps",
            status=FocusStatus.ACTIVE,
            createdAt="2026-08-07T14:00:00-07:00",
            updatedAt="2026-08-07T14:01:00-07:00",
        )
        with patch(
            "app.focus.canonical_work_context_source.get_state",
            return_value=active_state,
        ):
            response = get_canonical_active_session()

        self.assertEqual(response["provider"], "canonical-focus")
        self.assertEqual(response["activeSession"]["id"], "focus-new")
        self.assertEqual(
            response["activeSession"]["goal"],
            "summarize progress and next steps",
        )

        for terminal_status in (FocusStatus.INACTIVE, FocusStatus.COMPLETE):
            with self.subTest(status=terminal_status):
                terminal_state = active_state.model_copy(
                    update={"status": terminal_status}
                )
                with patch(
                    "app.focus.canonical_work_context_source.get_state",
                    return_value=terminal_state,
                ):
                    response = get_canonical_active_session()
                self.assertIsNone(response["activeSession"])

    def test_installer_redirects_work_context_away_from_memory_session(self) -> None:
        from app import work_context

        original = work_context.get_active_session
        try:
            install_canonical_work_context_source()
            self.assertIs(
                work_context.get_active_session,
                get_canonical_active_session,
            )
        finally:
            work_context.get_active_session = original

    def test_main_installs_canonical_source_before_background_middleware(self) -> None:
        source = MAIN_SOURCE.read_text(encoding="utf-8")
        install_index = source.index("install_canonical_work_context_source()")
        background_index = source.index(
            "from app.background_context_middleware import BackgroundWorkContextMiddleware"
        )
        focus_middleware_index = source.index(
            "from app.focus.middleware import FocusShadowMiddleware"
        )
        self.assertLess(install_index, background_index)
        self.assertLess(install_index, focus_middleware_index)

    def test_existing_planner_seed_calls_are_harmless_under_retired_loader(self) -> None:
        planner_source = PLANNER_SOURCE.read_text(encoding="utf-8")
        legacy_source = (
            REPO_ROOT / "backend" / "app" / "focus" / "legacy.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "seed_from_legacy(load_legacy_focus_seed())",
            planner_source,
        )
        self.assertIn(
            "if not _legacy_focus_bootstrap_enabled():\n        return None",
            legacy_source,
        )

    def test_work_context_legacy_read_seam_is_redirectable(self) -> None:
        source = WORK_CONTEXT_SOURCE.read_text(encoding="utf-8")
        self.assertIn("response = get_active_session()", source)
        self.assertIn(
            'session = response.get("activeSession") if isinstance(response, dict) else None',
            source,
        )


if __name__ == "__main__":
    unittest.main()
