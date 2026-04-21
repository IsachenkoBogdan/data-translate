from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.config.models_dataset_translation import TranslationRuleModel
from data_translate.domain.translation_markers import build_marked_text, parse_marked_translation


@dataclass(frozen=True)
class StrategyResult:
    value: Any
    error: str = ""
    attempts: int = 0


Options = Mapping[str, Any]


def rule_options(rule: TranslationRuleModel) -> dict[str, Any]:
    return dict(rule.options)


def merge_translation_errors(*parts: str) -> str:
    return "; ".join(part for part in parts if part)


async def translate_marked_items(items: list[str], adapter: TranslationAdapter) -> tuple[list[str] | None, int, str]:
    if not items:
        return [], 0, ""
    whole = await adapter.translate(build_marked_text(items), use_cache=False)
    if whole.status == "ok" and whole.text is not None:
        try:
            return parse_marked_translation(whole.text, len(items)), whole.attempts, ""
        except ValueError as exc:
            return None, whole.attempts, f"whole-list parse failed: {exc}"
    return None, whole.attempts, whole.error


async def translate_items_with_fallback(items: list[str], adapter: TranslationAdapter, *, use_cache: bool) -> tuple[list[str], int, list[str]]:
    translated_items: list[str] = []
    attempts = 0
    errors: list[str] = []
    for idx, item in enumerate(items):
        result = await adapter.translate(item, use_cache=use_cache)
        attempts += result.attempts
        if result.status == "ok" and result.text is not None:
            translated_items.append(result.text)
        else:
            translated_items.append(item)
            errors.append(f"item {idx}: {result.error}")
    return translated_items, attempts, errors


async def translate_sequence(
    items: list[str],
    adapter: TranslationAdapter,
    *,
    use_cache: bool,
) -> tuple[list[str], int, str]:
    if not items:
        return [], 0, ""

    translated_items, attempts, error = await translate_marked_items(items, adapter)
    if translated_items is not None:
        return translated_items, attempts, error

    fallback_items, fallback_attempts, fallback_errors = await translate_items_with_fallback(
        items,
        adapter,
        use_cache=use_cache,
    )
    return fallback_items, attempts + fallback_attempts, merge_translation_errors(error, *fallback_errors)
