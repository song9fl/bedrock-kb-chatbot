from __future__ import annotations

import re
from typing import Any


SUMMARY_PREFIXES = (
    "common math topics",
    "for 5th grade",
    "for 8th grade",
    "for 13-year-olds",
    "for grade",
    "here's",
    "here’s",
    "here is",
    "to teach",
    "to make math more engaging",
    "you can create math problems",
    "you can explore",
)


CONFIRMATION_PATTERNS = (
    "is that right",
    "was i right",
    "am i right",
    "did i get it",
    "is this correct",
    "is that correct",
    "correct?",
    "right?",
)


HELP_SEEKING_PATTERNS = (
    "what do i do then",
    "what do i do",
    "what next",
    "how do i",
    "how should i",
    "what now",
)


RESET_PATTERNS = (
    "start over",
    "reset",
    "too complicated",
    "i don't want that topic anymore",
    "i don't want uno anymore",
)


CLOSING_PATTERNS = (
    "thanks",
    "thank you",
    "got it",
    "ok",
    "okay",
    "bye",
    "dismiss",
)


def enforce_coach_style(user_query: str, assistant_text: str, citations: list[dict[str, Any]] | None = None) -> str:
    del citations

    query = normalize_text(user_query).lower()
    text = normalize_text(assistant_text)
    if not text:
        return "Let's focus on one idea at a time. What part do you want to work on first?"

    if is_closing_query(query):
        return trim_to_sentences(text, 2) or "You're welcome."

    cleaned = strip_summary_leads(text)

    if is_summary_style(text):
        cleaned = rewrite_summary_dump(query, cleaned)
    else:
        cleaned = trim_to_sentences(cleaned, 3)
        cleaned = ensure_direct_response(query, cleaned)

    if not cleaned.endswith("?") and not is_closing_query(query):
        cleaned = cleaned.rstrip(".")
        cleaned = f"{cleaned} What part do you want to work on first?"

    return cleaned.strip()


def is_closing_query(query: str) -> bool:
    return any(pattern in query for pattern in CLOSING_PATTERNS)


def is_confirmation_query(query: str) -> bool:
    return any(pattern in query for pattern in CONFIRMATION_PATTERNS)


def is_help_seeking_query(query: str) -> bool:
    return any(pattern in query for pattern in HELP_SEEKING_PATTERNS)


def is_reset_query(query: str) -> bool:
    return any(pattern in query for pattern in RESET_PATTERNS)


def is_summary_style(text: str) -> bool:
    lowered = text.strip().lower()
    if any(lowered.startswith(prefix) for prefix in SUMMARY_PREFIXES):
        return True

    first_sentence = first_sentence_text(lowered)
    return bool(
        first_sentence
        and (
            first_sentence.startswith("common math topics")
            or first_sentence.startswith("for ")
            or first_sentence.startswith("here's")
            or first_sentence.startswith("here is")
            or first_sentence.startswith("to teach")
        )
    )


def strip_summary_leads(text: str) -> str:
    cleaned = text.strip()
    patterns = [
        r"^(common math topics[^:]*:\s*)",
        r"^(for \d{1,2}(?:st|nd|rd|th)? grade(?: students)?[^:]*:\s*)",
        r"^(for \d{1,2}-year-olds[^:]*:\s*)",
        r"^(here(?:'|’)s[^:]*:\s*)",
        r"^(here is[^:]*:\s*)",
        r"^(to teach[^:]*:\s*)",
        r"^(to make math more engaging[^:]*:\s*)",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def rewrite_summary_dump(query: str, text: str) -> str:
    if is_confirmation_query(query):
        prefix = "Not quite." if looks_negative(text) else "Yes, you're right."
        return f"{prefix} Let's focus on one idea at a time. What part do you want to work on first?"

    if is_help_seeking_query(query) or is_reset_query(query):
        return "Start with one small step. What part feels most confusing right now?"

    if "solve" in query or "how" in query or "what" in query:
        return "Let's focus on one idea at a time. What part do you want to work on first?"

    compact = trim_to_sentences(text, 2)
    if not compact:
        compact = "Let's focus on one idea at a time."
    if compact.endswith("?"):
        return compact
    return f"{compact.rstrip('.')} What part do you want to work on first?"


def ensure_direct_response(query: str, text: str) -> str:
    if is_confirmation_query(query):
        if not starts_with_direct_confirmation(text):
            return f"{confirmation_prefix(text)} {text}".strip()
    if is_help_seeking_query(query):
        if not starts_with_directive(text):
            return f"Start with one small step: {text}".strip()
    return text


def confirmation_prefix(text: str) -> str:
    lowered = text.strip().lower()
    if lowered.startswith(("no", "not quite", "incorrect", "wrong", "almost")) or looks_negative(text):
        return "Not quite."
    return "Yes, you're right."


def starts_with_direct_confirmation(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered.startswith(("yes", "no", "not quite", "almost", "correct", "incorrect", "right"))


def starts_with_directive(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered.startswith(("start", "first", "try", "begin", "check", "look", "identify", "find"))


def looks_negative(text: str) -> bool:
    lowered = text.strip().lower()[:120]
    return any(word in lowered for word in ("incorrect", "not quite", "wrong", "doesn't", "does not", "cannot", "can't"))


def trim_to_sentences(text: str, max_sentences: int) -> str:
    sentences = split_sentences(text)
    if not sentences:
        return text.strip()
    return " ".join(sentences[:max_sentences]).strip()


def split_sentences(text: str) -> list[str]:
    stripped = text.strip()
    if not stripped:
        return []
    parts = re.split(r"(?<=[.!?])\s+", stripped)
    return [part.strip() for part in parts if part.strip()]


def first_sentence_text(text: str) -> str:
    sentences = split_sentences(text)
    return sentences[0].lower() if sentences else ""


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()
