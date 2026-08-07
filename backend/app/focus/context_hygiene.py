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
    "goal",
    "outcome",
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
    return removals


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


def _question_is_generic_outcome(question: str) -> bool:
    tokens = set(semantic_tokens(question))
    return bool(tokens & _GENERIC_OUTCOME_WORDS)


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
        return field in {"requirements", "preferences", "decisions"}

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
