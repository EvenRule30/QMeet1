from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Literal

from app.focus.models import PendingQuestion

ContextFieldName = Literal[
    "requirements",
    "constraints",
    "preferences",
    "decisions",
    "knownFacts",
]

_NUMBER_WORDS = {
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
}

_IRREGULAR_STEMS = {
    "checked": "check",
    "checking": "check",
    "found": "find",
    "finding": "find",
    "confirmed": "confirm",
    "confirming": "confirm",
    "completed": "complete",
    "completing": "complete",
    "planned": "plan",
    "planning": "plan",
    "chosen": "choose",
    "chose": "choose",
    "wrote": "write",
    "written": "write",
    "identified": "identify",
    "identifying": "identify",
    "available": "available",
}

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "against",
    "are",
    "as",
    "at",
    "be",
    "been",
    "being",
    "by",
    "did",
    "do",
    "does",
    "for",
    "from",
    "has",
    "have",
    "having",
    "i",
    "in",
    "into",
    "is",
    "it",
    "its",
    "me",
    "my",
    "of",
    "on",
    "our",
    "that",
    "the",
    "their",
    "them",
    "this",
    "to",
    "user",
    "we",
    "was",
    "were",
    "with",
    "you",
    "your",
}

_QUESTION_WORDS = {
    "what",
    "which",
    "who",
    "where",
    "when",
    "why",
    "how",
    "would",
    "could",
    "should",
    "make",
    "makes",
    "really",
}

_GENERIC_OUTCOME_WORDS = {
    "accomplish",
    "accomplishment",
    "achieve",
    "achiev",
    "aim",
    "goal",
    "objective",
    "outcome",
    "purpose",
    "result",
    "success",
    "successful",
    "win",
}

_POLARITY_WORDS = {
    "above",
    "after",
    "before",
    "below",
    "less",
    "more",
    "no",
    "not",
    "over",
    "under",
    "without",
}

# Phase 20W: semantic duplicates and semantic corrections are different.
# A changed number/date must not be called a duplicate, but explicit correction
# language may supersede one earlier value that occupies the same context slot.
_CORRECTION_PATTERN = re.compile(
    r"(?:^|\b)(?:actually|instead|rather|correction|correcting|"
    r"change that|changed that|make that|update that|revise that|"
    r"I meant|we meant|scratch that)(?:\b|$)",
    re.IGNORECASE,
)
_REFERENTIAL_CORRECTION_PATTERN = re.compile(
    r"\b(?:change|make|update|revise)\s+that\b|\b(?:instead|rather)\b",
    re.IGNORECASE,
)

_CONTEXT_SLOT_TOKENS: dict[str, set[str]] = {
    "budget": {
        "budget",
        "cost",
        "costs",
        "dollar",
        "money",
        "price",
        "pricing",
        "spend",
        "spending",
    },
    "deadline": {
        "cutoff",
        "deadline",
        "due",
        "finish",
        "ready",
    },
    "availability": {
        "availability",
        "available",
        "free",
        "unavailable",
    },
}


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _stem_token(token: str) -> str:
    if token in _IRREGULAR_STEMS:
        return _IRREGULAR_STEMS[token]
    if len(token) > 5 and token.endswith("ies"):
        return f"{token[:-3]}y"
    if len(token) > 4 and token.endswith("ing"):
        base = token[:-3]
        if len(base) > 2 and base[-1:] == base[-2:-1]:
            base = base[:-1]
        return base
    if len(token) > 4 and token.endswith("ed"):
        base = token[:-2]
        if base.endswith("i"):
            return f"{base[:-1]}y"
        return base
    if len(token) > 4 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def semantic_tokens(value: object) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKC", _clean_text(value)).casefold()
    text = re.sub(r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)", r" \1 dollar ", text)
    text = text.replace(",", "")
    raw_tokens = re.findall(r"[a-z0-9]+", text)
    tokens: list[str] = []
    for raw_token in raw_tokens:
        token = _NUMBER_WORDS.get(raw_token, raw_token)
        if not token or token in _STOP_WORDS:
            continue
        token = _stem_token(token)
        if not token or token in _STOP_WORDS:
            continue
        tokens.append(token)
    return tuple(tokens)


def semantic_key(value: object) -> str:
    return " ".join(semantic_tokens(value))


def _numeric_tokens(tokens: Iterable[str]) -> set[str]:
    return {token for token in tokens if token.isdigit()}


def _polarity_tokens(tokens: Iterable[str]) -> set[str]:
    return {token for token in tokens if token in _POLARITY_WORDS}


def _context_slots(value: object) -> set[str]:
    tokens = set(semantic_tokens(value))
    slots: set[str] = set()
    for slot, slot_tokens in _CONTEXT_SLOT_TOKENS.items():
        if tokens & slot_tokens:
            slots.add(slot)
    return slots


def _looks_like_correction(value: object) -> bool:
    return bool(_CORRECTION_PATTERN.search(_clean_text(value)))


def _referential_correction(value: object) -> bool:
    return bool(_REFERENTIAL_CORRECTION_PATTERN.search(_clean_text(value)))


def superseded_values_to_remove(
    values: Iterable[str],
    preferred: str,
) -> list[str]:
    """Return prior context values explicitly superseded by ``preferred``.

    This is deliberately narrower than semantic duplicate detection. Different
    numeric/date values remain distinct unless the incoming wording clearly
    signals a correction. We then remove only one safe predecessor:

    - the sole existing value in the same semantic slot (budget/deadline/etc.),
      or
    - the most recent value for an explicit referential correction such as
      ``make that Thursday``.

    Ambiguous corrections across multiple same-slot values are preserved rather
    than guessed.
    """

    cleaned_preferred = _clean_text(preferred)
    items = [_clean_text(value) for value in values if _clean_text(value)]
    if not cleaned_preferred or not items or not _looks_like_correction(cleaned_preferred):
        return []

    preferred_slots = _context_slots(cleaned_preferred)
    if preferred_slots:
        same_slot = [
            item
            for item in items
            if _context_slots(item) & preferred_slots
            and not semantically_equivalent(item, cleaned_preferred)
        ]
        if len(same_slot) == 1:
            return same_slot

    if _referential_correction(cleaned_preferred):
        latest = items[-1]
        if not semantically_equivalent(latest, cleaned_preferred):
            return [latest]

    return []


def semantic_similarity(left: object, right: object) -> float:
    left_text = _clean_text(left)
    right_text = _clean_text(right)
    if not left_text or not right_text:
        return 0.0
    if left_text.casefold() == right_text.casefold():
        return 1.0

    left_tokens = set(semantic_tokens(left_text))
    right_tokens = set(semantic_tokens(right_text))
    if not left_tokens or not right_tokens:
        return 0.0
    left_numbers = _numeric_tokens(left_tokens)
    right_numbers = _numeric_tokens(right_tokens)
    if (left_numbers or right_numbers) and left_numbers != right_numbers:
        return 0.0

    left_polarity = _polarity_tokens(left_tokens)
    right_polarity = _polarity_tokens(right_tokens)
    if left_polarity and right_polarity and left_polarity != right_polarity:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    minimum = min(len(left_tokens), len(right_tokens))
    union = len(left_tokens | right_tokens)
    if intersection < 2:
        return 0.0

    containment = intersection / minimum
    jaccard = intersection / union
    if containment >= 0.8:
        return containment
    if intersection >= 3 and jaccard >= 0.6:
        return jaccard
    return 0.0


def semantically_equivalent(left: object, right: object) -> bool:
    return semantic_similarity(left, right) >= 0.8


def find_semantic_match(values: Iterable[str], candidate: str) -> str | None:
    cleaned_candidate = _clean_text(candidate)
    if not cleaned_candidate:
        return None

    items = [_clean_text(value) for value in values if _clean_text(value)]
    for item in items:
        if item.casefold() == cleaned_candidate.casefold():
            return item
    best_item: str | None = None
    best_score = 0.0
    for item in items:
        score = semantic_similarity(item, cleaned_candidate)
        if score > best_score:
            best_item = item
            best_score = score
    return best_item if best_score >= 0.8 else None


def _preferred_group_value(group: list[str], preferred: str | None) -> str:
    if preferred:
        for value in group:
            if value.casefold() == preferred.casefold():
                return value
    return min(
        group,
        key=lambda value: (len(semantic_tokens(value)), len(value), group.index(value)),
    )


def duplicate_values_to_remove(
    values: Iterable[str],
    *,
    preferred: str | None = None,
) -> list[str]:
    items = [_clean_text(value) for value in values if _clean_text(value)]
    groups: list[list[str]] = []
    for item in items:
        matching_group = next(
            (
                group
                for group in groups
                if any(semantically_equivalent(item, member) for member in group)
            ),
            None,
        )
        if matching_group is None:
            groups.append([item])
        else:
            matching_group.append(item)

    removals: list[str] = []
    for group in groups:
        if len(group) < 2:
            continue
        preferred_for_group = (
            preferred
            if preferred
            and any(semantically_equivalent(preferred, member) for member in group)
            else None
        )
        keep = _preferred_group_value(group, preferred_for_group)
        kept_once = False
        for value in group:
            if value.casefold() == keep.casefold() and not kept_once:
                kept_once = True
                continue
            removals.append(value)

    if preferred:
        removals.extend(superseded_values_to_remove(items, preferred))

    unique_removals: list[str] = []
    seen: set[str] = set()
    for value in removals:
        key = value.casefold()
        if not value or key in seen:
            continue
        seen.add(key)
        unique_removals.append(value)
    return unique_removals


def equivalent_values_to_remove(
    values: Iterable[str],
    preferred: str,
) -> list[str]:
    cleaned_preferred = _clean_text(preferred)
    if not cleaned_preferred:
        return []
    return [
        _clean_text(value)
        for value in values
        if _clean_text(value)
        and _clean_text(value).casefold() != cleaned_preferred.casefold()
        and semantically_equivalent(value, cleaned_preferred)
    ]


def question_is_generic_outcome(question: str) -> bool:
    """Return whether a coaching question asks for the Focus's desired outcome.

    Phase 20W4 broadens the deterministic vocabulary to cover natural coaching
    prompts such as "What would you like this meeting to accomplish?" while
    keeping the decision token-based and independent of the model classifier.
    """
    tokens = set(semantic_tokens(question))
    return bool(tokens & _GENERIC_OUTCOME_WORDS)


def _question_is_generic_outcome(question: str) -> bool:
    # Backward-compatible private alias for the existing Phase 20W3 call sites.
    return question_is_generic_outcome(question)


def question_answered_by_focus_update(
    pending_question: PendingQuestion | None,
    *,
    field: Literal["objective", "title", "mode"],
    value: str,
) -> bool:
    """Return whether an explicit lifecycle update resolves the pending question.

    Phase 20W3 keeps this deliberately narrow. A non-empty objective update is
    authoritative for a generic success/outcome question. Title and mode edits
    never clear coaching questions, and specific questions remain owned by their
    normal context-answer path.
    """
    if pending_question is None or field != "objective":
        return False
    if not _clean_text(value):
        return False
    question = _clean_text(pending_question.question)
    return bool(question) and _question_is_generic_outcome(question)


def question_answered_by_context(
    pending_question: PendingQuestion | None,
    *,
    field: ContextFieldName,
    value: str,
) -> bool:
    if pending_question is None:
        return False

    answer_tokens = set(semantic_tokens(value))
    if not answer_tokens:
        return False
    question = _clean_text(pending_question.question)
    if not question:
        return False

    explicit_answer_language = bool(answer_tokens & _GENERIC_OUTCOME_WORDS) or any(
        phrase in _clean_text(value).casefold()
        for phrase in ("would make", "means", "a win", "successful if")
    )
    if explicit_answer_language:
        return True

    if _question_is_generic_outcome(question):
        # Phase 20W3: field type is not evidence that the user answered a
        # success/outcome question. Only explicit outcome language above, or a
        # verified objective update via question_answered_by_focus_update(), may
        # clear this generic coaching question.
        return False
    question_tokens = set(semantic_tokens(question)) - _QUESTION_WORDS
    if not question_tokens:
        return False

    if question_tokens & {"budget", "cost", "money", "price"}:
        return field in {"constraints", "knownFacts", "decisions"} and bool(
            answer_tokens & {"budget", "cost", "money", "price", "dollar"}
            or _numeric_tokens(answer_tokens)
        )
    if question_tokens & {"day", "date", "time", "available", "availability"}:
        return field in {"knownFacts", "constraints", "decisions"} and bool(
            answer_tokens & {"day", "date", "time", "available", "availability"}
            or _numeric_tokens(answer_tokens)
        )

    overlap = question_tokens & answer_tokens
    required_overlap = 1 if len(question_tokens) <= 4 else 2
    return len(overlap) >= required_overlap
