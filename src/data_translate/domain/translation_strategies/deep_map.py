from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.domain.translation_common import DEFAULT_MAX_CHUNK_CHARS, Options, StrategyResult, translate_sequence


Container = dict[str, Any] | list[Any]
Key = str | int
TextRef = tuple[Container, Key, str]


def _append_key(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _append_index(path: str, index: int) -> str:
    return f"{path}[{index}]" if path else f"[{index}]"


def _excluded_keys(options: Options) -> set[str]:
    raw = options.get("exclude_keys", [])
    if raw is None:
        return set()
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, list):
        return {str(item) for item in raw}
    return {str(raw)}


def _collect_text_refs(value: Any, *, exclude_keys: set[str], path: str = "") -> list[TextRef]:
    refs: list[TextRef] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in exclude_keys:
                continue
            item_path = _append_key(path, str(key))
            if isinstance(item, str):
                if item.strip():
                    refs.append((value, key, item_path))
            elif isinstance(item, (dict, list)):
                refs.extend(_collect_text_refs(item, exclude_keys=exclude_keys, path=item_path))
        return refs

    if isinstance(value, list):
        for idx, item in enumerate(value):
            item_path = _append_index(path, idx)
            if isinstance(item, str):
                if item.strip():
                    refs.append((value, idx, item_path))
            elif isinstance(item, (dict, list)):
                refs.extend(_collect_text_refs(item, exclude_keys=exclude_keys, path=item_path))
    return refs


def deep_map_text_pairs(
    source_value: Any,
    translated_value: Any,
    *,
    exclude_keys: set[str],
) -> tuple[list[tuple[str, str, str]], list[str]]:
    source_refs = _collect_text_refs(source_value, exclude_keys=exclude_keys)
    translated_refs = _collect_text_refs(translated_value, exclude_keys=exclude_keys)
    translated_by_path = {path: str(container[key] or "") for container, key, path in translated_refs}
    pairs: list[tuple[str, str, str]] = []
    errors: list[str] = []

    for source_container, source_key, path in source_refs:
        if path not in translated_by_path:
            errors.append(f"missing translated text at {path}")
            continue
        pairs.append((path, str(source_container[source_key] or ""), translated_by_path[path]))

    extra_paths = sorted(set(translated_by_path) - {path for _container, _key, path in source_refs})
    if extra_paths:
        errors.append(f"extra translated text paths: {extra_paths[:20]}")
    return pairs, errors


def validate_deep_map_input(value: Any, options: Options, *, field_name: str) -> str:
    del options
    if value is None or isinstance(value, (Mapping, list)):
        return ""
    return f"field {field_name!r} with strategy 'deep_map_texts' must be a mapping, list, or null, got {type(value).__name__}"


async def translate_deep_map(
    value: Any,
    adapter: TranslationAdapter,
    options: Options,
    *,
    use_cache: bool,
) -> StrategyResult:
    if value is None:
        return StrategyResult(value=None, error="", attempts=0)

    output = deepcopy(value)
    refs = _collect_text_refs(output, exclude_keys=_excluded_keys(options))
    if not refs:
        return StrategyResult(value=output, error="", attempts=0)

    texts = [str(container[key] or "") for container, key, _path in refs]
    translated_texts, attempts, error = await translate_sequence(
        texts,
        adapter,
        use_cache=use_cache,
        max_chunk_chars=int(options.get("max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS)),
    )
    for (container, key, _path), translated in zip(refs, translated_texts, strict=True):
        container[key] = translated
    return StrategyResult(value=output, error=error, attempts=attempts)
