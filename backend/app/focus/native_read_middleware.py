from __future__ import annotations

import json
import os
import re
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.focus.planner import focus_mode
from app.focus.route_bridge import (
    focus_read_intent,
    memory_mutation_intent,
    memory_read_intent,
    visual_read_intent,
)


_MAX_BODY_BYTES = 1_000_000
_ADDITIVE_MEMORY_OPERATIONS = frozenset({"save_note", "save_task"})

_PROTECTED_REQUEST_PREFIX = (
    r"(?:(?:please\s+)?(?:can|could|would|will)\s+you\s+(?:please\s+)?|"
    r"please\s+|"
    r"i\s+(?:want|need)\s+you\s+to\s+)?"
)
_CLEAR_ALL_MY_NOTES_PATTERN = re.compile(
    rf"^{_PROTECTED_REQUEST_PREFIX}"
    r"(?:clear|delete|remove|wipe)\s+all\s+my\s+notes?$",
    re.IGNORECASE,
)
_START_NEW_FOCUS_PATTERN = re.compile(
    rf"^{_PROTECTED_REQUEST_PREFIX}"
    r"(?:start|begin|create|open)\s+"
    r"(?:(?:a|the|my)\s+)?new\s+"
    r"(?:(?P<mode>general|coding|code|development|dev|programming|"
    r"meeting|planning|research|personal)\s+)?"
    r"(?:focus\s+session|focus|session|focus\s+mode)"
    r"(?:\s+(?:for|on|about|around|called|named|to|"
    r"with(?:\s+the)?\s+goal\s+(?:of|to))\s+(?P<title>.+))?$",
    re.IGNORECASE,
)
_FOCUS_MODE_ALIASES = {
    "code": "coding",
    "development": "coding",
    "dev": "coding",
    "programming": "coding",
}


def _rollout_mode(environment_name: str) -> str:
    value = os.getenv(environment_name, "shadow").strip().casefold()
    if value in {"guarded", "active", "on", "enabled", "true", "1"}:
        return "guarded"
    if value in {"off", "disabled", "false", "0"}:
        return "off"
    return "shadow"


def native_read_route_mode() -> str:
    """Return the configured native read-route rollout mode."""

    return _rollout_mode("QMEET_FOCUS_NATIVE_READ_MODE")


def native_write_route_mode() -> str:
    """Return the configured native additive-write rollout mode.

    Only reversible note creation and task creation are eligible. Destructive
    mutations and every external-system write stay on the existing path.
    """

    return _rollout_mode("QMEET_FOCUS_NATIVE_WRITE_MODE")


def native_read_routes_enabled() -> bool:
    return focus_mode() == "active" and native_read_route_mode() == "guarded"


def native_write_routes_enabled() -> bool:
    return focus_mode() == "active" and native_write_route_mode() == "guarded"


def protected_command_routes_enabled() -> bool:
    """Return whether deterministic protected-command recovery is enabled.

    This safety net follows the already-enabled guarded route rollout. It does
    not broaden native write ownership: it only converts known protected
    phrases into existing frontend commands so they cannot fall through to
    ordinary chat and falsely narrate a mutation.
    """

    return focus_mode() == "active" and _rollout_mode(
        "QMEET_FOCUS_ROUTE_MODE"
    ) == "guarded"


def native_command_routes_enabled() -> bool:
    return (
        native_read_routes_enabled()
        or native_write_routes_enabled()
        or protected_command_routes_enabled()
    )


def _visual_read_intent_with_recipient_alias(message: str):
    """Recognize visual reads that include the natural recipient word ``me``."""

    intent = visual_read_intent(message)
    if intent is not None:
        return intent

    canonical_message = re.sub(
        r"\b(show|read|list|display|open)\s+me\s+",
        r"\1 ",
        str(message or ""),
        count=1,
        flags=re.IGNORECASE,
    )
    if canonical_message == message:
        return None
    return visual_read_intent(canonical_message)


def native_read_route_payload(message: str) -> dict[str, Any] | None:
    """Build existing frontend command payloads for safe local reads only."""

    focus_intent = focus_read_intent(message)
    if focus_intent is not None:
        payload: dict[str, str] = {"mode": focus_intent.mode}
        if focus_intent.timeframe:
            payload["timeframe"] = focus_intent.timeframe
        return {
            "intent": "command",
            "action": focus_intent.action,
            "confidence": 0.99,
            "frontendCommand": focus_intent.frontend_command,
            "payload": payload,
            "reason": (
                "Native Focus read routing recognized a safe read of "
                "synchronized Focus memory."
            ),
        }

    memory_intent = memory_read_intent(message)
    if memory_intent is not None:
        return {
            "intent": "command",
            "action": memory_intent.action,
            "confidence": 0.99,
            "frontendCommand": memory_intent.frontend_command,
            "payload": {"surface": memory_intent.surface},
            "reason": (
                "Native Focus read routing recognized a safe read of "
                "synchronized Notes or Tasks memory."
            ),
        }

    visual_intent = _visual_read_intent_with_recipient_alias(message)
    if visual_intent is not None:
        return {
            "intent": "command",
            "action": visual_intent.action,
            "confidence": 0.99,
            "frontendCommand": visual_intent.frontend_command,
            "payload": {"mode": visual_intent.mode},
            "reason": (
                "Native Focus read routing recognized a safe read of already "
                "saved visual context."
            ),
        }

    return None


def native_write_route_payload(message: str) -> dict[str, Any] | None:
    """Build a frontend command payload for reversible additive memory writes.

    This is intentionally limited to creating one note or creating one task.
    Completion, deletion, clearing, Calendar writes, visual mutations, and
    Focus lifecycle changes remain excluded.
    """

    intent = memory_mutation_intent(message)
    if intent is None or intent.operation not in _ADDITIVE_MEMORY_OPERATIONS:
        return None
    if not intent.payload.strip():
        return None

    return {
        "intent": "command",
        "action": intent.action,
        "confidence": 0.99,
        "frontendCommand": intent.frontend_command,
        "payload": {
            "operation": intent.operation,
            "value": intent.payload,
        },
        "reason": (
            "Native Focus write routing recognized a reversible additive "
            "Notes or Tasks memory write."
        ),
    }


def _normalize_protected_message(message: str) -> str:
    normalized = re.sub(r"[?!,;]+", " ", str(message or "").strip())
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip(" .")


def protected_command_route_payload(message: str) -> dict[str, Any] | None:
    """Recover exact protected mutations before they can become chat.

    These payloads intentionally use existing frontend commands. The frontend
    therefore keeps its normal confirmation requirement for clearing notes and
    its canonical Focus-session persistence path for starting a new Focus.
    """

    normalized = _normalize_protected_message(message)
    if not normalized:
        return None

    if _CLEAR_ALL_MY_NOTES_PATTERN.fullmatch(normalized):
        return {
            "intent": "command",
            "action": "clear_notes",
            "confidence": 0.99,
            "frontendCommand": "clear notes",
            "payload": {
                "operation": "clear_notes",
                "requiresConfirmation": True,
            },
            "reason": (
                "Deterministic protected routing recognized a destructive "
                "Notes clear request and preserved the frontend confirmation "
                "gate."
            ),
        }

    focus_match = _START_NEW_FOCUS_PATTERN.fullmatch(normalized)
    if focus_match is None:
        return None

    raw_mode = str(focus_match.group("mode") or "general").casefold()
    mode = _FOCUS_MODE_ALIASES.get(raw_mode, raw_mode)
    raw_title = str(focus_match.group("title") or "").strip(" .")
    title = raw_title or (
        f"{mode.capitalize()} focus" if mode != "general" else "Focus session"
    )
    mode_prefix = "" if mode == "general" else f"{mode} "

    return {
        "intent": "command",
        "action": "start_focus_session",
        "confidence": 0.99,
        "frontendCommand": f"start {mode_prefix}focus for {title}",
        "payload": {
            "operation": "start_focus",
            "mode": mode,
            "title": title,
        },
        "reason": (
            "Deterministic protected routing recognized an explicit new Focus "
            "request and routed it through the canonical Focus-session "
            "persistence path."
        ),
    }


def native_command_route_payload(
    message: str,
) -> tuple[dict[str, Any] | None, str]:
    """Return the eligible payload and its native command-source label."""

    if protected_command_routes_enabled():
        protected_payload = protected_command_route_payload(message)
        if protected_payload is not None:
            return protected_payload, "focus-protected-command"

    if native_read_routes_enabled():
        read_payload = native_read_route_payload(message)
        if read_payload is not None:
            return read_payload, "focus-native-read"

    if native_write_routes_enabled():
        write_payload = native_write_route_payload(message)
        if write_payload is not None:
            return write_payload, "focus-native-write"

    return None, ""


def _header_value(scope: Scope, name: bytes) -> str:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() == name:
            return raw_value.decode("latin-1", errors="ignore")
    return ""


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        chunk = message.get("body", b"")
        if chunk:
            total += len(chunk)
            if total > _MAX_BODY_BYTES:
                return b""
            chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay_receive(body: bytes, original_receive: Receive) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }
        return await original_receive()

    return receive


def _json_payload(body: bytes, content_type: str) -> dict[str, Any]:
    if not body or "application/json" not in content_type.casefold():
        return {}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _send_native_response(
    payload: dict[str, Any],
    send: Send,
    *,
    command_source: str,
) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
                (
                    b"x-qmeet-command-source",
                    command_source.encode("ascii", errors="ignore"),
                ),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        }
    )


class FocusNativeReadRouteMiddleware:
    """Bypass the legacy command model for narrowly proven local commands.

    The historical class name is retained to avoid a middleware migration.
    Read ownership remains unchanged. Phase 20B additionally permits only two
    reversible additive writes: save one note and create one task. A narrow
    protected-command recovery gate also prevents known destructive or Focus
    lifecycle phrases from falling through to ordinary chat.

    This middleware must remain inside FocusShadowMiddleware. The outer Focus
    middleware still creates shared turn plans, records route telemetry, and
    preserves the existing fallback architecture.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if (
            scope["type"] != "http"
            or scope.get("path", "") != "/api/command/interpret"
            or str(scope.get("method", "GET")).upper() != "POST"
            or not native_command_routes_enabled()
        ):
            await self.app(scope, receive, send)
            return

        body = await _read_body(receive)
        replay_receive = _replay_receive(body, receive)
        request_payload = _json_payload(
            body,
            _header_value(scope, b"content-type"),
        )
        user_message = str(request_payload.get("message") or "").strip()
        native_payload, command_source = native_command_route_payload(
            user_message
        )
        if native_payload is None:
            await self.app(scope, replay_receive, send)
            return

        await _send_native_response(
            native_payload,
            send,
            command_source=command_source,
        )
