from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "src" / "app" / "App.tsx"
OBSERVER = REPO_ROOT / "src" / "app" / "lib" / "agentShadowObserver.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_app_imports_shadow_observer_and_comparison_reporter() -> None:
    text = _read(APP)
    assert "observeAgentShadowTurn" in text
    assert "reportAgentShadowLegacyRoute" in text


def test_shadow_observation_is_top_level_only() -> None:
    text = _read(APP)
    assert "commandRoute === 'exact' && !forcedCommandMatch" in text


def test_shadow_observation_uses_visible_user_turn_not_internal_command() -> None:
    text = _read(APP)
    shadow_start = text.index("const shadowTurn = commandRoute === 'exact'")
    shadow_end = text.index("let shadowRouteSequence = 0;", shadow_start)
    block = text[shadow_start:shadow_end]
    assert "userMessage: visibleUserText" in block
    assert "userMessage: trimmed" not in block


def test_shadow_observation_starts_before_existing_routing_side_effects() -> None:
    text = _read(APP)
    observer_index = text.index("const shadowTurn = commandRoute === 'exact'")
    stop_speech_index = text.index("stopCurrentSpeech();", observer_index)
    pending_route_index = text.index("if (pendingInterpreterCommand)", observer_index)
    assert observer_index < stop_speech_index < pending_route_index


def test_shadow_observation_does_not_block_current_route() -> None:
    text = _read(APP)
    assert "await observeAgentShadowTurn" not in text
    assert "const shadowTurn = commandRoute === 'exact'" in text


def test_shadow_request_uses_observational_endpoint() -> None:
    text = _read(OBSERVER)
    assert "${QMEET_API_BASE_URL}/api/agent/shadow/decide" in text
    assert "method: 'POST'" in text


def test_shadow_request_includes_recent_conversation_and_ui_context() -> None:
    text = _read(OBSERVER)
    assert "recentConversation: buildRecentConversation(options.recentMessages)" in text
    assert "activePanel: options.activePanel" in text
    assert "chatActive: options.chatActive" in text
    assert "observationPoint: 'frontend-pre-route'" in text


def test_tool_cards_are_preserved_as_tool_context() -> None:
    text = _read(OBSERVER)
    assert "message.role === 'assistant' && message.variant === 'tool'" in text
    assert "return { role: 'tool', content };" in text


def test_shadow_observer_and_comparison_are_fail_open() -> None:
    text = _read(OBSERVER)
    assert text.count("Existing routing remains authoritative.") >= 2
    assert "throw error" not in text


def test_pending_confirmation_and_focus_projection_are_advisory_context() -> None:
    app = _read(APP)
    observer = _read(OBSERVER)
    assert "pendingCommand: pendingInterpreterCommand" in app
    assert "frontendFocusProjection: activeSession" in app
    assert "pendingCommand: options.pendingCommand" in observer
    assert "originalText: pendingInterpreterCommand.originalText" in app
    assert "frontendFocusProjection: options.frontendFocusProjection" in observer


def test_legacy_route_is_reported_after_shadow_decision_with_sequence() -> None:
    app = _read(APP)
    assert "let shadowRouteSequence = 0;" in app
    assert "shadowRouteSequence += 1;" in app
    assert "void reportAgentShadowLegacyRoute(shadowTurn" in app
    assert "sequence: shadowRouteSequence" in app


def test_late_comparison_uses_dedicated_endpoint() -> None:
    observer = _read(OBSERVER)
    assert "${QMEET_API_BASE_URL}/api/agent/shadow/compare" in observer
    assert "const shadow = await shadowTurn;" in observer
    assert "turnId: shadow.turnId" in observer
