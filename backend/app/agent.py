import os
from dataclasses import dataclass

import openai
from openai import AsyncOpenAI


SYSTEM_PROMPT = """
You are QMeet, a concise AI assistant inside a small 1024x600 tablet orb interface.

Behavior:
- Keep answers short enough to read on a small tablet screen.
- Be direct and useful.
- Prefer 1-3 short paragraphs.
- Avoid long lists unless the user asks for detail.
- Do not mention backend, API, provider, or implementation details unless asked.
- If asked what you are, say you are QMeet, the orb assistant.
""".strip()


# Simple in-memory history for the current backend process.
# This resets when the backend restarts.
MESSAGE_HISTORY: list[dict[str, str]] = []


@dataclass
class AgentConfig:
    provider: str
    model: str
    max_output_tokens: int
    has_openai_key: bool


class AgentUserFacingError(Exception):
    """Safe error message that can be shown in the UI."""


def get_agent_config() -> AgentConfig:
    provider = os.getenv("LLM_PROVIDER", "mock").lower().strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()

    try:
        max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "300"))
    except ValueError:
        max_output_tokens = 300

    # OpenAI currently documents 16 as the minimum for max_output_tokens.
    max_output_tokens = max(16, min(max_output_tokens, 1200))

    return AgentConfig(
        provider=provider,
        model=model,
        max_output_tokens=max_output_tokens,
        has_openai_key=bool(os.getenv("OPENAI_API_KEY")),
    )


def get_public_status() -> dict:
    config = get_agent_config()

    return {
        "ok": True,
        "provider": config.provider,
        "model": config.model if config.provider == "openai" else "mock",
        "hasOpenAIKey": config.has_openai_key,
        "maxOutputTokens": config.max_output_tokens,
    }


def reset_conversation() -> None:
    global MESSAGE_HISTORY
    MESSAGE_HISTORY.clear()
    

async def generate_reply(message: str) -> str:
    config = get_agent_config()

    if config.provider == "mock":
        return mock_reply(message)

    if config.provider == "openai":
        return await openai_reply(message, config)

    raise AgentUserFacingError(
        f'Unsupported LLM_PROVIDER="{config.provider}". Use "mock" or "openai".'
    )


def mock_reply(message: str) -> str:
    text = message.strip()

    if not text:
        return "I did not receive a message."

    return (
        "QMeet backend is connected. "
        f'You said: "{text}". '
    )


async def openai_reply(message: str, config: AgentConfig) -> str:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise AgentUserFacingError(
            "OpenAI is selected, but OPENAI_API_KEY is missing in backend/.env."
        )

    client = AsyncOpenAI(api_key=api_key)

    # Keep recent context small for now.
    recent_history = MESSAGE_HISTORY[-10:]

    input_messages = [
        {
            "role": "developer",
            "content": SYSTEM_PROMPT,
        },
        *recent_history,
        {
            "role": "user",
            "content": message,
        },
    ]

    try:
        response = await client.responses.create(
            model=config.model,
            input=input_messages,
            max_output_tokens=config.max_output_tokens,
        )
    except openai.AuthenticationError as exc:
        raise AgentUserFacingError(
            "OpenAI authentication failed. Check backend/.env and verify the API key."
        ) from exc
    except openai.RateLimitError as exc:
        raise AgentUserFacingError(
            "OpenAI rate limit or quota was reached. Check API billing, limits, or try again later."
        ) from exc
    except openai.APIConnectionError as exc:
        raise AgentUserFacingError(
            "Could not connect to OpenAI. Check your internet connection."
        ) from exc
    except openai.APIError as exc:
        raise AgentUserFacingError(
            "OpenAI returned an API error. Try again shortly."
        ) from exc

    reply = response.output_text.strip()

    if not reply:
        raise AgentUserFacingError("The model returned an empty response.")


    MESSAGE_HISTORY.append({"role": "user", "content": message})
    MESSAGE_HISTORY.append({"role": "assistant", "content": reply})

    return reply