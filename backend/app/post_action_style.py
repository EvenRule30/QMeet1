from __future__ import annotations

import re

# Generic post-action tails add noise after a verified tool card. They are safe
# to remove because they do not describe the action that just occurred.
_TRAILING_OFFER_PATTERNS = (
    re.compile(r"(?:\s+|^)(?:Would you like\b[^?]*\?\s*)$", re.IGNORECASE),
    re.compile(
        r"(?:\s+|^)(?:If you(?:'d| would) like,?\s+I can\b[^.!?]*(?:[.!?])\s*)$",
        re.IGNORECASE,
    ),
    re.compile(r"(?:\s+|^)(?:Let me know if\b[^.!?]*(?:[.!?])\s*)$", re.IGNORECASE),
    re.compile(
        r"(?:\s+|^)(?:If you want\b[^.!?]*\b(?:let me know|I can help)\b[^.!?]*(?:[.!?])\s*)$",
        re.IGNORECASE,
    ),
    re.compile(r"(?:\s+|^)(?:I can also\b[^.!?]*(?:[.!?])\s*)$", re.IGNORECASE),
    re.compile(
        r"(?:\s+|^)(?:I can help (?:you )?\b[^.!?]*(?:[.!?])\s*)$",
        re.IGNORECASE,
    ),
    # Models also advertise follow-up capabilities declaratively, e.g.
    # "You can now manage it further or add more tasks if needed." Strip only
    # tails that begin with "You can" and contain an obvious follow-up
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

# Phase 21I2b: successful global-task continuations sometimes explain internal
# Focus relationship bookkeeping even though the verified tool receipt already
# says the task was saved globally. This is implementation detail, not a useful
# next-step consequence for the user.
_TRAILING_BOOKKEEPING_PATTERNS = (
    re.compile(
        r"(?:\s+|^)(?:It (?:is|was) not linked to (?:an|the|any) active focus session\.\s*)$",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:\s+|^)(?:The task (?:is|was) not linked to (?:an|the|any) active focus session\.\s*)$",
        re.IGNORECASE,
    ),
)


def compact_success_continuation(text: str) -> str:
    """Remove generic trailing chatter from a successful continuation.

    The verified tool card already tells the user what happened. This helper
    deliberately preserves substantive consequences/explanations and does not
    summarize or rewrite them. It only strips recognized generic follow-up
    offers/capability ads and narrow implementation bookkeeping that appears at
    the tail of an otherwise-complete success acknowledgement.
    """

    cleaned = re.sub(r"[ \t]+", " ", (text or "").strip())
    if not cleaned:
        return ""

    patterns = _TRAILING_OFFER_PATTERNS + _TRAILING_BOOKKEEPING_PATTERNS
    previous = None
    while cleaned != previous:
        previous = cleaned
        for pattern in patterns:
            cleaned = pattern.sub("", cleaned).strip()

    return cleaned
