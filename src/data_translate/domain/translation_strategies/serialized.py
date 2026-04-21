import json
from collections.abc import Mapping
from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.domain.translation_common import Options, StrategyResult, translate_sequence


def _validate_dialog_payload(value: Any, *, field_name: str, content_field: str) -> tuple[list[dict[str, Any]] | None, str]:
    if not isinstance(value, str):
        return None, f"field {field_name!r} with strategy 'serialized_dialog_turns_content' must be a string, got {type(value).__name__}"
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        return None, f"field {field_name!r} with strategy 'serialized_dialog_turns_content' must be valid JSON: {exc}"
    if not isinstance(payload, list):
        return None, (
            f"field {field_name!r} with strategy 'serialized_dialog_turns_content' must decode to a list, "
            f"got {type(payload).__name__}"
        )
    for idx, turn in enumerate(payload):
        if not isinstance(turn, Mapping):
            return None, (
                f"field {field_name!r} with strategy 'serialized_dialog_turns_content' must decode to a list of mappings; "
                f"item {idx} has type {type(turn).__name__}"
            )
        if content_field not in turn:
            return None, (
                f"field {field_name!r} with strategy 'serialized_dialog_turns_content' requires key "
                f"{content_field!r} in every turn; item {idx} is missing it"
            )
    return [dict(turn) for turn in payload], ""


def validate_serialized_dialog_turns_content_input(value: Any, options: Options, *, field_name: str) -> str:
    content_field = str(options.get("content_field", "content"))
    _payload, error = _validate_dialog_payload(value, field_name=field_name, content_field=content_field)
    return error


async def translate_serialized_dialog_turns_content(
    value: Any,
    adapter: TranslationAdapter,
    options: Options,
    *,
    use_cache: bool,
) -> StrategyResult:
    content_field = str(options.get("content_field", "content"))
    target_content_field = str(options.get("target_content_field", "content_fr"))
    payload, error = _validate_dialog_payload(value, field_name="value", content_field=content_field)
    if payload is None:
        return StrategyResult(value=value, error=error, attempts=0)

    contents = [str(turn.get(content_field) or "") for turn in payload]
    translated_contents, attempts, translate_error = await translate_sequence(contents, adapter, use_cache=use_cache)
    translated_payload: list[dict[str, Any]] = []
    for original_turn, translated_content in zip(payload, translated_contents, strict=True):
        turn = dict(original_turn)
        turn[target_content_field] = translated_content
        translated_payload.append(turn)

    return StrategyResult(
        value=json.dumps(translated_payload, ensure_ascii=False),
        error=translate_error,
        attempts=attempts,
    )
