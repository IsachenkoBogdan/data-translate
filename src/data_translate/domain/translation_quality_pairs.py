import json
from typing import Any

from datasets import DatasetDict

from data_translate.domain.translation_quality_models import QualityRule
from data_translate.domain.translation_strategies.deep_map import deep_map_text_pairs
from data_translate.domain.translation_strategies.nested import nested_text_pairs


TextPair = tuple[str, str, str]


def text_pairs(source_value: Any, translated_value: Any, strategy: str, options: dict[str, Any]) -> tuple[list[TextPair], list[str]]:
    if strategy == "deep_map_texts":
        raw_exclude_keys = options.get("exclude_keys", [])
        if isinstance(raw_exclude_keys, str):
            exclude_keys = {raw_exclude_keys}
        elif isinstance(raw_exclude_keys, list):
            exclude_keys = {str(item) for item in raw_exclude_keys}
        else:
            exclude_keys = set()
        return deep_map_text_pairs(source_value, translated_value, exclude_keys=exclude_keys)
    if strategy == "nested_text_fields":
        return nested_text_pairs(source_value, translated_value, [str(path) for path in options.get("paths", [])])
    if strategy == "serialized_dialog_turns_content":
        return _serialized_dialog_pairs(source_value, translated_value, options)
    if strategy == "dialog_turns_content":
        return _dialog_pairs(source_value, translated_value, options)
    if isinstance(source_value, list) or isinstance(translated_value, list):
        return _list_pairs(source_value, translated_value)
    return [("", str(source_value or ""), str(translated_value or ""))], []


def _list_pairs(source_value: Any, translated_value: Any) -> tuple[list[TextPair], list[str]]:
    if not isinstance(source_value, list) or not isinstance(translated_value, list):
        return [], [f"type mismatch: {type(source_value).__name__} -> {type(translated_value).__name__}"]
    pairs = [
        (f"[{idx}]", str(source_item or ""), str(translated_item or ""))
        for idx, (source_item, translated_item) in enumerate(zip(source_value, translated_value, strict=False))
    ]
    errors = []
    if len(source_value) != len(translated_value):
        errors.append(f"length mismatch: {len(source_value)} -> {len(translated_value)}")
    return pairs, errors


def _dialog_pairs(source_value: Any, translated_value: Any, options: dict[str, Any]) -> tuple[list[TextPair], list[str]]:
    content_field = str(options.get("content_field", "content"))
    if not isinstance(source_value, list) or not isinstance(translated_value, list):
        return [], [f"type mismatch: {type(source_value).__name__} -> {type(translated_value).__name__}"]
    pairs: list[TextPair] = []
    for idx, (source_turn, translated_turn) in enumerate(zip(source_value, translated_value, strict=False)):
        if isinstance(source_turn, dict):
            source_text = source_turn.get(content_field, "")
        else:
            source_text = source_turn
        if isinstance(translated_turn, dict):
            translated_text = translated_turn.get(content_field, "")
        else:
            translated_text = translated_turn
        pairs.append((f"[{idx}].{content_field}", str(source_text or ""), str(translated_text or "")))
    errors = []
    if len(source_value) != len(translated_value):
        errors.append(f"length mismatch: {len(source_value)} -> {len(translated_value)}")
    return pairs, errors


def _serialized_dialog_pairs(source_value: Any, translated_value: Any, options: dict[str, Any]) -> tuple[list[TextPair], list[str]]:
    content_field = str(options.get("content_field", "content"))
    target_content_field = str(options.get("target_content_field", content_field))
    try:
        source_payload = json.loads(str(source_value or "[]"))
        translated_payload = json.loads(str(translated_value or "[]"))
    except json.JSONDecodeError as exc:
        return [], [f"json parse failed: {exc}"]
    if not isinstance(source_payload, list) or not isinstance(translated_payload, list):
        return [], ["serialized value must decode to lists"]
    pairs: list[TextPair] = []
    for idx, (source_turn, translated_turn) in enumerate(zip(source_payload, translated_payload, strict=False)):
        if not isinstance(source_turn, dict) or not isinstance(translated_turn, dict):
            continue
        pairs.append(
            (
                f"[{idx}].{target_content_field}",
                str(source_turn.get(content_field, "") or ""),
                str(translated_turn.get(target_content_field, "") or ""),
            )
        )
    errors = []
    if len(source_payload) != len(translated_payload):
        errors.append(f"length mismatch: {len(source_payload)} -> {len(translated_payload)}")
    return pairs, errors


def inferred_rules(translated: DatasetDict) -> list[QualityRule]:
    rules: dict[tuple[str, str], QualityRule] = {}
    for split_dataset in translated.values():
        columns = set(split_dataset.column_names)
        for column in columns:
            if not column.endswith("_fr"):
                continue
            source = column.removesuffix("_fr")
            if source in columns:
                rules[(source, column)] = QualityRule(source=source, target=column, strategy="auto")
    return list(rules.values())
