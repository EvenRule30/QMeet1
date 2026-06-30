import os


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
    # Optional provider. Only used when LLM_PROVIDER=openai.
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    response = await client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You are QMeet, a concise AI assistant running inside a "
                    "tablet orb interface. Keep responses useful and readable "
                    "on a small 1024x600 screen."
                ),
            },
            {
                "role": "user",
                "content": message,
            },
        ],
    )

    return response.output_text