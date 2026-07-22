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
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

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
            ObserveTurnRequest(message=message, source=source, apply=True),
            turn_id=turn_id,
        )
    except Exception:
        LOGGER.exception("Focus shadow observation failed")


def _search_summary(payload: dict[str, Any], query: str) -> tuple[bool, str, list[str]]:
    success = bool(payload.get("ok", True))
    summary = str(payload.get("summary") or payload.get("message") or "").strip()
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
            identifier = str(source.get("url") or source.get("title") or "").strip()
            if identifier and identifier not in result_ids:
                result_ids.append(identifier[:500])
            if len(result_ids) >= 30:
                break
    return success, summary[:2000], result_ids


class FocusShadowMiddleware:
    """Observe turns and tool results without changing legacy behavior.

    QMEET_FOCUS_MODE=off disables it. The initial rollout uses shadow mode;
    active routing will be added only after transcript regression tests pass.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
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

        if path == "/api/command/interpret":
            response_complete = asyncio.Event()

            async def passthrough_send(message: Message) -> None:
                await send(message)
                if message["type"] == "http.response.body" and not message.get(
                    "more_body", False
                ):
                    response_complete.set()

            await self.app(scope, replay_receive, passthrough_send)
            await response_complete.wait()

            user_message = str(request_payload.get("message") or "").strip()
            if user_message:
                asyncio.create_task(
                    _observe_safely(
                        user_message,
                        source="command-interpret-shadow",
                        turn_id=_turn_id(scope),
                    )
                )
            return

        response_status = 500
        response_content_type = ""
        response_chunks: list[bytes] = []

        async def capture_send(message: Message) -> None:
            nonlocal response_status, response_content_type
            if message["type"] == "http.response.start":
                response_status = int(message.get("status", 500))
                for raw_name, raw_value in message.get("headers", []):
                    if raw_name.lower() == b"content-type":
                        response_content_type = raw_value.decode(
                            "latin-1", errors="ignore"
                        )
            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk and sum(map(len, response_chunks)) + len(chunk) <= _MAX_BODY_BYTES:
                    response_chunks.append(chunk)
            await send(message)

        await self.app(scope, replay_receive, capture_send)

        query = str(request_payload.get("query") or "").strip()
        response_payload = _json_payload(
            b"".join(response_chunks), response_content_type
        )
        success, summary, result_ids = _search_summary(response_payload, query)
        success = success and 200 <= response_status < 300
        try:
            record_tool_result(
                tool=ToolName.SEARCH,
                success=success,
                summary=summary,
                result_ids=result_ids,
                source_turn_id=_turn_id(scope),
                source="search-router-result",
            )
        except Exception:
            LOGGER.exception("Focus could not assimilate Search result")
