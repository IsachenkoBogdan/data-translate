from collections.abc import Mapping
from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.domain.translation_common import Options, StrategyResult, translate_sequence


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
    del options
    text = str(value or "")
    result = await adapter.translate(text, use_cache=use_cache)
    translated = result.text if result.status == "ok" and result.text is not None else text
    return StrategyResult(value=translated, error=result.error, attempts=result.attempts)


async def translate_text_list(value: Any, adapter: TranslationAdapter, options: Options, *, use_cache: bool) -> StrategyResult:
    del options
    items = [str(item) for item in (value or [])]
    translated_items, attempts, error = await translate_sequence(items, adapter, use_cache=use_cache)
    return StrategyResult(translated_items, error=error, attempts=attempts)
