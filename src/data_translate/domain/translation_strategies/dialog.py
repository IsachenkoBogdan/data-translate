from collections.abc import Mapping
from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.domain.translation_common import Options, StrategyResult, translate_sequence


def _dialog_contents(dialog: list[Any], *, content_field: str, normalize_newlines: bool) -> list[str]:
    contents: list[str] = []
    for turn in dialog:
        content = str(turn.get(content_field) or "") if isinstance(turn, Mapping) else str(turn)
        if normalize_newlines:
            content = content.replace("\n", " ").strip()
        contents.append(content)
    return contents


def _dialog_with_translated_contents(dialog: list[Any], translated_contents: list[str], *, content_field: str) -> list[Any]:
    translated_dialog: list[Any] = []
    for original_turn, translated_content in zip(dialog, translated_contents, strict=True):
        if isinstance(original_turn, Mapping):
            new_turn = dict(original_turn)
            new_turn[content_field] = translated_content
            translated_dialog.append(new_turn)
        else:
            translated_dialog.append(translated_content)
    return translated_dialog


def validate_dialog_turns_content_input(value: Any, options: Options, *, field_name: str) -> str:
    content_field = str(options.get("content_field", "content"))
    if not isinstance(value, list):
        return f"field {field_name!r} with strategy 'dialog_turns_content' must be a list, got {type(value).__name__}"
    for idx, turn in enumerate(value):
        if not isinstance(turn, Mapping):
            return (
                f"field {field_name!r} with strategy 'dialog_turns_content' must contain mappings; "
                f"item {idx} has type {type(turn).__name__}"
            )
        if content_field not in turn:
            return (
                f"field {field_name!r} with strategy 'dialog_turns_content' requires key "
                f"{content_field!r} in every turn; item {idx} is missing it"
            )
    return ""


async def translate_dialog_turns_content(
    value: Any,
    adapter: TranslationAdapter,
    options: Options,
    *,
    use_cache: bool,
) -> StrategyResult:
    dialog = list(value or [])
    content_field = str(options.get("content_field", "content"))
    normalize_newlines = bool(options.get("normalize_newlines", True))
    contents = _dialog_contents(dialog, content_field=content_field, normalize_newlines=normalize_newlines)
    translated_contents, attempts, error = await translate_sequence(contents, adapter, use_cache=use_cache)
    return StrategyResult(
        _dialog_with_translated_contents(dialog, translated_contents, content_field=content_field),
        error=error,
        attempts=attempts,
    )
