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
from data_translate.domain.translation_unchanged import retry_if_unchanged


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
    retry_text, retry_attempts, retry_error = await retry_if_unchanged(text, translated, adapter, options)
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
        retry_text, retry_attempts, retry_error = await retry_if_unchanged(source, translated, adapter, options)
        attempts += retry_attempts
        translated_items[idx] = retry_text
        if retry_error:
            retry_errors.append(f"item {idx}: {retry_error}")
    return StrategyResult(translated_items, error=merge_translation_errors(error, *retry_errors), attempts=attempts)
