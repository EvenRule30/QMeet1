from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.focus.models import ObserveTurnRequest, ToolName
from app.focus.planner import focus_mode, observe_turn
from app.focus.store import record_tool_result

LOGGER = logging.getLogger("qmeet.focus.middleware")

_MAX_BODY_BYTES = 1_000_000
_OBSERVATION_TASKS: dict[str, asyncio.Task[None]] = {}


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


def _replay_receive(body: bytes) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent

        if sent:
            return {
                "type": "http.request",
                "body": b"",
                "more_body": False,
            }

        sent = True
        return {
            "type": "http.request",
            "body": body,
            "more_body": False,
        }

    return receive


def _json_payload(body: bytes, content_type: str) -> dict[str, Any]:
    if not body or "application/json" not in content_type.casefold():
        return {}

    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _turn_id(scope: Scope) -> str:
    supplied = _header_value(scope, b"x-qmeet-turn-id").strip()
    return supplied[:120] if supplied else f"focus-turn-{uuid4().hex}"


async def _observe_safely(message: str, source: str, turn_id: str) -> None:
    try:
        await observe_turn(
            ObserveTurnRequest(
                message=message,
                source=source,
                apply=True,
            ),
            turn_id=turn_id,
        )
    except Exception:
        LOGGER.exception(
            "Focus shadow observation failed for turn %s",
            turn_id,
        )


def _start_observation(
    message: str,
    *,
    source: str,
    turn_id: str,
) -> asyncio.Task[None]:
    existing = _OBSERVATION_TASKS.get(turn_id)
    if existing is not None and not existing.done():
        return existing

    task = asyncio.create_task(
        _observe_safely(
            message,
            source=source,
            turn_id=turn_id,
        ),
        name=f"qmeet-focus-observe-{turn_id}",
    )
    _OBSERVATION_TASKS[turn_id] = task

    def remove_completed_task(completed: asyncio.Task[None]) -> None:
        if _OBSERVATION_TASKS.get(turn_id) is completed:
            _OBSERVATION_TASKS.pop(turn_id, None)

    task.add_done_callback(remove_completed_task)
    return task


async def _wait_for_observation(turn_id: str) -> None:
    task = _OBSERVATION_TASKS.get(turn_id)
    if task is None:
        return

    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception(
            "Focus observation ordering wait failed for turn %s",
            turn_id,
        )


def _search_summary(
    payload: dict[str, Any],
    query: str,
) -> tuple[bool, str, list[str]]:
    success = bool(payload.get("ok", True))
    summary = str(
        payload.get("summary")
        or payload.get("message")
        or ""
    ).strip()
    recommendation = str(payload.get("recommendation") or "").strip()

    if recommendation and recommendation not in summary:
        summary = f"{summary} {recommendation}".strip()

    if not summary:
        summary = (
            f"Search completed for: {query}."
            if success
            else f"Search failed for: {query}."
        )

    result_ids: list[str] = []
    sources = payload.get("sources")

    if isinstance(sources, list):
        for source in sources:
            if not isinstance(source, dict):
                continue

            identifier = str(
                source.get("url")
                or source.get("title")
                or ""
            ).strip()

            if identifier and identifier not in result_ids:
                result_ids.append(identifier[:500])

            if len(result_ids) >= 30:
                break

    return success, summary[:2000], result_ids


async def _record_search_result_safely(
    *,
    turn_id: str,
    success: bool,
    summary: str,
    result_ids: list[str],
) -> None:
    try:
        # A Search response can complete before the separate model planner does.
        # Waiting here keeps the event log ordered as:
        # turn_planned -> tool_requested -> tool_completed.
        # This task runs after the visible Search response has already been sent.
        await _wait_for_observation(turn_id)

        record_tool_result(
            tool=ToolName.SEARCH,
            success=success,
            summary=summary,
            result_ids=result_ids,
            source_turn_id=turn_id,
            source="search-router-result",
        )
    except Exception:
        LOGGER.exception(
            "Focus could not assimilate Search result for turn %s",
            turn_id,
        )


class FocusShadowMiddleware:
    """Observe turns and tool results without changing legacy behavior.

    QMEET_FOCUS_MODE=off disables it. The initial rollout uses shadow mode;
    active routing will be added only after transcript regression tests pass.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http" or focus_mode() == "off":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path not in {"/api/command/interpret", "/api/search"}:
            await self.app(scope, receive, send)
            return

        request_body = await _read_body(receive)
        content_type = _header_value(scope, b"content-type")
        request_payload = _json_payload(request_body, content_type)
        replay_receive = _replay_receive(request_body)
        turn_id = _turn_id(scope)

        if path == "/api/command/interpret":
            user_message = str(
                request_payload.get("message") or ""
            ).strip()

            if user_message:
                # Register the task before the command response can trigger a
                # follow-up Search request carrying the same turn ID.
                _start_observation(
                    user_message,
                    source="command-interpret-shadow",
                    turn_id=turn_id,
                )

            await self.app(scope, replay_receive, send)
            return

        query = str(request_payload.get("query") or "").strip()

        if query:
            # Exact frontend search commands bypass /api/command/interpret.
            # Observe the Search request itself so the turn still receives a
            # structured plan and shares its ID with the eventual tool result.
            _start_observation(
                query,
                source="search-request-shadow",
                turn_id=turn_id,
            )

        response_status = 500
        response_content_type = ""
        response_chunks: list[bytes] = []
        response_size = 0

        async def capture_send(message: Message) -> None:
            nonlocal response_status
            nonlocal response_content_type
            nonlocal response_size

            if message["type"] == "http.response.start":
                response_status = int(message.get("status", 500))

                for raw_name, raw_value in message.get("headers", []):
                    if raw_name.lower() == b"content-type":
                        response_content_type = raw_value.decode(
                            "latin-1",
                            errors="ignore",
                        )

            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk and response_size + len(chunk) <= _MAX_BODY_BYTES:
                    response_chunks.append(chunk)
                    response_size += len(chunk)

            await send(message)

        await self.app(scope, replay_receive, capture_send)

        response_payload = _json_payload(
            b"".join(response_chunks),
            response_content_type,
        )
        success, summary, result_ids = _search_summary(
            response_payload,
            query,
        )
        success = success and 200 <= response_status < 300

        # Do not delay the already-sent Search response while the shadow planner
        # finishes. The background task preserves event ordering instead.
        asyncio.create_task(
            _record_search_result_safely(
                turn_id=turn_id,
                success=success,
                summary=summary,
                result_ids=result_ids,
            ),
            name=f"qmeet-focus-search-result-{turn_id}",
        )
