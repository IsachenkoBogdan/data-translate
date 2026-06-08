from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.domain.translation_common import DEFAULT_MAX_CHUNK_CHARS, Options, StrategyResult, translate_sequence


PathRef = tuple[dict[str, Any], str, str]


def _append_key(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else f".{key}"


def _append_index(prefix: str, idx: int) -> str:
    return f"{prefix}[{idx}]" if prefix else f"[{idx}]"


def _path_segments(path: str) -> list[str]:
    return [segment for segment in path.split(".") if segment]


def _iter_refs(node: Any, segments: list[str], prefix: str = "") -> list[PathRef]:
    if not segments:
        return []

    segment = segments[0]
    rest = segments[1:]

    if segment == "[]":
        if not isinstance(node, list):
            return []
        refs: list[PathRef] = []
        for idx, item in enumerate(node):
            refs.extend(_iter_refs(item, rest, _append_index(prefix, idx)))
        return refs

    if segment.endswith("[]"):
        key = segment[:-2]
        if not isinstance(node, Mapping):
            return []
        child = node.get(key)
        if not isinstance(child, list):
            return []
        refs = []
        key_prefix = _append_key(prefix, key)
        for idx, item in enumerate(child):
            refs.extend(_iter_refs(item, rest, _append_index(key_prefix, idx)))
        return refs

    if not isinstance(node, Mapping):
        return []
    if rest:
        return _iter_refs(node.get(segment), rest, _append_key(prefix, segment))
    if segment not in node:
        return []
    if not isinstance(node, dict):
        return []
    return [(node, segment, _append_key(prefix, segment))]


def _refs_for_paths(value: Any, paths: list[str]) -> list[PathRef]:
    refs: list[PathRef] = []
    seen: set[tuple[int, str]] = set()
    for path in paths:
        for container, key, label in _iter_refs(value, _path_segments(path)):
            identity = (id(container), key)
            if identity in seen:
                continue
            seen.add(identity)
            refs.append((container, key, label))
    return refs


def nested_text_pairs(source_value: Any, translated_value: Any, paths: list[str]) -> tuple[list[tuple[str, str, str]], list[str]]:
    source_refs = _refs_for_paths(source_value, paths)
    translated_refs = _refs_for_paths(translated_value, paths)
    pairs: list[tuple[str, str, str]] = []
    errors: list[str] = []
    if len(source_refs) != len(translated_refs):
        errors.append(f"nested path count mismatch: {len(source_refs)} -> {len(translated_refs)}")
    for (source_container, source_key, path), (translated_container, translated_key, _translated_path) in zip(
        source_refs,
        translated_refs,
        strict=False,
    ):
        pairs.append(
            (
                path,
                str(source_container.get(source_key) or ""),
                str(translated_container.get(translated_key) or ""),
            )
        )
    return pairs, errors


def _configured_paths(options: Options) -> list[str]:
    raw_paths = options.get("paths", [])
    if not isinstance(raw_paths, list):
        return []
    return [str(path) for path in raw_paths if str(path).strip()]


def validate_nested_text_fields_input(value: Any, options: Options, *, field_name: str) -> str:
    paths = _configured_paths(options)
    if not paths:
        return "strategy 'nested_text_fields' requires a non-empty options.paths list"
    if value is None or isinstance(value, (Mapping, list)):
        return ""
    return f"field {field_name!r} with strategy 'nested_text_fields' must be a mapping, list, or null, got {type(value).__name__}"


async def translate_nested_text_fields(
    value: Any,
    adapter: TranslationAdapter,
    options: Options,
    *,
    use_cache: bool,
) -> StrategyResult:
    paths = _configured_paths(options)
    if value is None:
        return StrategyResult(value=None, error="", attempts=0)

    translated_value = deepcopy(value)
    refs = _refs_for_paths(translated_value, paths)
    if not refs:
        return StrategyResult(value=translated_value, error="", attempts=0)

    items = [str(container.get(key) or "") for container, key, _path in refs]
    max_chunk_chars = int(options.get("max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS))
    translated_items, attempts, error = await translate_sequence(
        items,
        adapter,
        use_cache=use_cache,
        max_chunk_chars=max_chunk_chars,
    )
    for (container, key, _path), translated_item in zip(refs, translated_items, strict=True):
        if container.get(key) is not None:
            container[key] = translated_item
    return StrategyResult(value=translated_value, error=error, attempts=attempts)
