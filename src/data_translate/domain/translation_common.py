from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.config.models_dataset_translation import TranslationRuleModel
from data_translate.domain.text_processing.chunking import chunk_text
from data_translate.domain.translation_markers import build_marked_text, parse_marked_translation


@dataclass(frozen=True)
class StrategyResult:
    value: Any
    error: str = ""
    attempts: int = 0


Options = Mapping[str, Any]
DEFAULT_MAX_CHUNK_CHARS = 2500


def rule_options(rule: TranslationRuleModel) -> dict[str, Any]:
    return dict(rule.options)


def merge_translation_errors(*parts: str) -> str:
    return "; ".join(part for part in parts if part)


async def translate_text_with_chunks(
    text: str,
    adapter: TranslationAdapter,
    *,
    use_cache: bool,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> tuple[str, int, str]:
    if not text.strip():
        return text, 0, ""

    chunks = chunk_text(text, max_chars=max_chunk_chars)
    translated_chunks: list[str] = []
    attempts = 0
    errors: list[str] = []
    for idx, chunk in enumerate(chunks):
        result = await adapter.translate(chunk, use_cache=use_cache)
        attempts += result.attempts
        if result.status in {"ok", "empty"} and result.text is not None:
            translated_chunks.append(result.text)
        else:
            translated_chunks.append(chunk)
            errors.append(f"chunk {idx}: {result.error}")
    return "".join(translated_chunks), attempts, merge_translation_errors(*errors)


async def translate_marked_items(
    items: list[str],
    adapter: TranslationAdapter,
    *,
    use_cache: bool = False,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> tuple[list[str] | None, int, str]:
    if not items:
        return [], 0, ""
    marked_text = build_marked_text(items)
    if max_chunk_chars > 0 and len(marked_text) > max_chunk_chars:
        return None, 0, "marked text exceeds max_chunk_chars"
    whole = await adapter.translate(marked_text, use_cache=use_cache)
    if whole.status == "ok" and whole.text is not None:
        try:
            return parse_marked_translation(whole.text, len(items)), whole.attempts, ""
        except ValueError as exc:
            return None, whole.attempts, f"whole-list parse failed: {exc}"
    return None, whole.attempts, whole.error


def marked_item_batches(items: list[str], *, max_chunk_chars: int) -> list[tuple[int, list[str]]]:
    if not items:
        return []
    if max_chunk_chars <= 0:
        return [(0, items)]

    batches: list[tuple[int, list[str]]] = []
    start = 0
    current: list[str] = []
    for idx, item in enumerate(items):
        candidate = [*current, item]
        if current and len(build_marked_text(candidate)) > max_chunk_chars:
            batches.append((start, current))
            start = idx
            current = [item]
        else:
            current = candidate
    if current:
        batches.append((start, current))
    return batches


async def translate_marked_items_batched(
    items: list[str],
    adapter: TranslationAdapter,
    *,
    use_cache: bool,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> tuple[list[str], int, list[str]]:
    translated_items = list(items)
    attempts = 0
    errors: list[str] = []

    for start_idx, batch in marked_item_batches(items, max_chunk_chars=max_chunk_chars):
        batch_translated, batch_attempts, batch_error = await translate_marked_items(
            batch,
            adapter,
            use_cache=use_cache,
            max_chunk_chars=max_chunk_chars,
        )
        attempts += batch_attempts
        if batch_translated is not None:
            translated_items[start_idx : start_idx + len(batch)] = batch_translated
            continue

        fallback_items, fallback_attempts, fallback_errors = await translate_items_with_fallback(
            batch,
            adapter,
            use_cache=use_cache,
            max_chunk_chars=max_chunk_chars,
        )
        attempts += fallback_attempts
        translated_items[start_idx : start_idx + len(batch)] = fallback_items
        if fallback_errors:
            errors.append(f"items {start_idx}:{start_idx + len(batch)}: {batch_error}")
            errors.extend(f"item {start_idx + idx}: {error}" for idx, error in enumerate(fallback_errors))

    return translated_items, attempts, errors


async def translate_items_with_fallback(
    items: list[str],
    adapter: TranslationAdapter,
    *,
    use_cache: bool,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> tuple[list[str], int, list[str]]:
    translated_items: list[str] = []
    attempts = 0
    errors: list[str] = []
    for idx, item in enumerate(items):
        translated, item_attempts, error = await translate_text_with_chunks(
            item,
            adapter,
            use_cache=use_cache,
            max_chunk_chars=max_chunk_chars,
        )
        attempts += item_attempts
        translated_items.append(translated)
        if error:
            errors.append(f"item {idx}: {error}")
    return translated_items, attempts, errors


async def translate_sequence(
    items: list[str],
    adapter: TranslationAdapter,
    *,
    use_cache: bool,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
) -> tuple[list[str], int, str]:
    if not items:
        return [], 0, ""

    translated_items, attempts, error = await translate_marked_items(
        items,
        adapter,
        use_cache=False,
        max_chunk_chars=max_chunk_chars,
    )
    if translated_items is not None:
        return translated_items, attempts, error

    if error == "marked text exceeds max_chunk_chars":
        batched_items, batched_attempts, batched_errors = await translate_marked_items_batched(
            items,
            adapter,
            use_cache=use_cache,
            max_chunk_chars=max_chunk_chars,
        )
        if batched_errors:
            return batched_items, attempts + batched_attempts, merge_translation_errors(*batched_errors)
        return batched_items, attempts + batched_attempts, ""

    fallback_items, fallback_attempts, fallback_errors = await translate_items_with_fallback(
        items,
        adapter,
        use_cache=use_cache,
        max_chunk_chars=max_chunk_chars,
    )
    if fallback_errors:
        return fallback_items, attempts + fallback_attempts, merge_translation_errors(error, *fallback_errors)
    return fallback_items, attempts + fallback_attempts, ""
