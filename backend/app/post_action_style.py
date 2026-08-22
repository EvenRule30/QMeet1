from __future__ import annotations

import re

# Generic post-action offers add noise after a verified tool card. They are safe
# to remove because they do not describe the action that just occurred.
_TRAILING_OFFER_PATTERNS = (
    re.compile(r"(?:\s+|^)(?:Would you like\b[^?]*\?\s*)$", re.IGNORECASE),
    re.compile(
        r"(?:\s+|^)(?:If you(?:'d| would) like,?\s+I can\b[^.!?]*(?:[.!?])\s*)$",
        re.IGNORECASE,
    ),
    re.compile(r"(?:\s+|^)(?:Let me know if\b[^.!?]*(?:[.!?])\s*)$", re.IGNORECASE),
    re.compile(r"(?:\s+|^)(?:I can also\b[^.!?]*(?:[.!?])\s*)$", re.IGNORECASE),
    re.compile(
        r"(?:\s+|^)(?:I can help (?:you )?\b[^.!?]*(?:[.!?])\s*)$",
        re.IGNORECASE,
    ),
    # Phase 21I2a: models also advertise follow-up capabilities declaratively,
    # e.g. "You can now manage it further or add more tasks if needed." Strip
    # only tails that begin with "You can" and contain an obvious follow-up
    # management/action verb. A substantive consequence such as "You can now
    # access the saved PDF at ..." is intentionally not matched.
    re.compile(
        r"(?:\s+|^)(?:You can(?: now)?\s+"
        r"(?=[^.!?]*(?:\bmanage\b|\badd\b|\bcreate\b|\borganize\b|\blink\b|\breopen\b))"
        r"[^.!?]*(?:[.!?])\s*)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:\s+|^)(?:You can(?: now)?\s+"
        r"(?=[^.!?]*\bview\b)(?=[^.!?]*\bmanage\b)"
        r"[^.!?]*(?:[.!?])\s*)$",
        re.IGNORECASE,
    ),
)


def compact_success_continuation(text: str) -> str:
    """Remove only generic trailing offers from a successful continuation.

    The verified tool card already tells the user what happened. This helper
    deliberately preserves the substantive consequence/explanation and does
    not summarize, rewrite, or alter capability facts.
    """

    cleaned = re.sub(r"[ \t]+", " ", (text or "").strip())
    if not cleaned:
        return ""

    previous = None
    while cleaned != previous:
        previous = cleaned
        for pattern in _TRAILING_OFFER_PATTERNS:
            cleaned = pattern.sub("", cleaned).strip()

    return cleaned
