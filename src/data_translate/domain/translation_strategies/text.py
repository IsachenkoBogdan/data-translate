from collections.abc import Mapping
from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.domain.translation_common import (
    DEFAULT_MAX_CHUNK_CHARS,
    Options,
    StrategyResult,
    merge_translation_errors,
    translate_sequence,
    translate_text_with_chunks,
)


_ENGLISH_SIGNAL_WORDS = {
    "a",
    "am",
    "an",
    "and",
    "are",
    "be",
    "can",
    "could",
    "do",
    "does",
    "for",
    "have",
    "how",
    "i",
    "is",
    "it",
    "may",
    "my",
    "need",
    "not",
    "of",
    "offer",
    "on",
    "please",
    "should",
    "that",
    "the",
    "then",
    "this",
    "to",
    "try",
    "we",
    "what",
    "where",
    "will",
    "with",
    "you",
    "your",
}


def _normalized_for_unchanged_check(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _tokens(value: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in value.lower():
        if char.isalpha() or char == "'":
            current.append(char)
        elif current:
            tokens.append("".join(current).strip("'"))
            current = []
    if current:
        tokens.append("".join(current).strip("'"))
    return [token for token in tokens if token]


def _has_english_signal(value: str) -> bool:
    return any(token in _ENGLISH_SIGNAL_WORDS for token in _tokens(value))


def _letter_count(value: str) -> int:
    return sum(1 for char in value if char.isalpha())


def _is_suspicious_unchanged_translation(source: str, translated: str, options: Options) -> bool:
    if not bool(options.get("retry_unchanged", False)):
        return False
    min_letters = int(options.get("unchanged_min_letters", 12))
    if _letter_count(source) < min_letters:
        return False
    if not _has_english_signal(source):
        return False
    return _normalized_for_unchanged_check(source) == _normalized_for_unchanged_check(translated)


async def _retry_if_unchanged(
    source: str,
    translated: str,
    adapter: TranslationAdapter,
    options: Options,
) -> tuple[str, int, str]:
    if not _is_suspicious_unchanged_translation(source, translated, options):
        return translated, 0, ""
    retry = await adapter.translate(source, use_cache=False)
    if retry.status in {"ok", "empty"} and retry.text is not None:
        if not _is_suspicious_unchanged_translation(source, retry.text, options):
            return retry.text, retry.attempts, ""
    return translated, retry.attempts, "unchanged translation"


def validate_text_input(value: Any, options: Options, *, field_name: str) -> str:
    del options
    if value is None or isinstance(value, (str, int, float, bool)):
        return ""
    return f"field {field_name!r} with strategy 'text' must be a scalar text-like value, got {type(value).__name__}"


def validate_text_list_input(value: Any, options: Options, *, field_name: str) -> str:
    del options
    if not isinstance(value, list):
        return f"field {field_name!r} with strategy 'text_list' must be a list, got {type(value).__name__}"
    for idx, item in enumerate(value):
        if isinstance(item, (list, tuple, Mapping)):
            return (
                f"field {field_name!r} with strategy 'text_list' must contain only scalar text-like items; "
                f"item {idx} has type {type(item).__name__}"
            )
    return ""


async def translate_text(value: Any, adapter: TranslationAdapter, options: Options, *, use_cache: bool) -> StrategyResult:
    text = str(value or "")
    max_chunk_chars = int(options.get("max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS))
    translated, attempts, error = await translate_text_with_chunks(
        text,
        adapter,
        use_cache=use_cache,
        max_chunk_chars=max_chunk_chars,
    )
    retry_text, retry_attempts, retry_error = await _retry_if_unchanged(text, translated, adapter, options)
    return StrategyResult(
        value=retry_text,
        error=merge_translation_errors(error, retry_error),
        attempts=attempts + retry_attempts,
    )


async def translate_text_list(value: Any, adapter: TranslationAdapter, options: Options, *, use_cache: bool) -> StrategyResult:
    items = [str(item) for item in (value or [])]
    max_chunk_chars = int(options.get("max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS))
    translated_items, attempts, error = await translate_sequence(
        items,
        adapter,
        use_cache=use_cache,
        max_chunk_chars=max_chunk_chars,
    )
    retry_errors: list[str] = []
    for idx, (source, translated) in enumerate(zip(items, translated_items, strict=True)):
        retry_text, retry_attempts, retry_error = await _retry_if_unchanged(source, translated, adapter, options)
        attempts += retry_attempts
        translated_items[idx] = retry_text
        if retry_error:
            retry_errors.append(f"item {idx}: {retry_error}")
    return StrategyResult(translated_items, error=merge_translation_errors(error, *retry_errors), attempts=attempts)
