import os
from openai import AsyncOpenAI


SYSTEM_PROMPT = """
You are QMeet, a concise AI assistant inside a small 1024x600 tablet orb interface.

Behavior:
- Keep answers short enough to read on a small tablet screen.
- Be direct and useful.
- Avoid long paragraphs unless the user asks for detail.
- Do not mention that you are an API or backend.
- If asked about the app/device, explain that you are the QMeet orb assistant.
"""

# Simple in-memory history for the current backend process.
# This resets when the backend restarts.
MESSAGE_HISTORY: list[dict[str, str]] = []

async def generate_reply(message: str) -> str:
    provider = os.getenv("LLM_PROVIDER", "mock").lower()

    if provider == "mock":
        return mock_reply(message)

    if provider == "openai":
        return await openai_reply(message)

    return f"Unknown LLM_PROVIDER={provider}. Falling back to mock reply: {mock_reply(message)}"


def mock_reply(message: str) -> str:
    text = message.strip()

    if not text:
        return "I did not receive a message."

    return (
        "QMeet backend is connected. "
        f'You said: "{text}". '
        "The next step is replacing this mock response with a real model call."
    )


async def openai_reply(message: str) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    if not api_key:
        return "OpenAI is selected, but OPENAI_API_KEY is missing in backend/.env."

    client = AsyncOpenAI(api_key=api_key)

    # Keep recent context small for now.
    recent_history = MESSAGE_HISTORY[-10:]

    input_messages = [
        {
            "role": "developer",
            "content": SYSTEM_PROMPT.strip(),
        },
        *recent_history,
        {
            "role": "user",
            "content": message,
        },
    ]

    response = await client.responses.create(
        model=model,
        input=input_messages,
        max_output_tokens=350,
    )

    reply = response.output_text.strip()

    MESSAGE_HISTORY.append({"role": "user", "content": message})
    MESSAGE_HISTORY.append({"role": "assistant", "content": reply})

    return reply