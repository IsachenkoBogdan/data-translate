from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.domain.text_processing.chunking import chunk_text
from data_translate.domain.text_processing.parsers import split_structured_entity
from data_translate.domain.translation_common import Options, StrategyResult, merge_translation_errors


DEFAULT_ENTITY_SEPARATOR = " <S> "
DEFAULT_MAX_CHUNK_CHARS = 4500


def validate_structured_entity_input(value: Any, options: Options, *, field_name: str) -> str:
    separator = str(options.get("separator", DEFAULT_ENTITY_SEPARATOR))
    if value is None or isinstance(value, str):
        return ""
    return f"field {field_name!r} with strategy 'structured_entity' must be a string, got {type(value).__name__}"


async def translate_structured_entity(
    value: Any,
    adapter: TranslationAdapter,
    options: Options,
    *,
    use_cache: bool,
) -> StrategyResult:
    separator = str(options.get("separator", DEFAULT_ENTITY_SEPARATOR))
    max_chunk_chars = int(options.get("max_chunk_chars", DEFAULT_MAX_CHUNK_CHARS))
    text = str(value or "")
    parsed = split_structured_entity(text, separator)
    if parsed is None:
        result = await adapter.translate(text, use_cache=use_cache)
        translated = result.text if result.status == "ok" and result.text is not None else text
        return StrategyResult(value=translated, error=result.error, attempts=result.attempts)

    name, tags, description = parsed
    if not description.strip():
        return StrategyResult(value=separator.join([name, tags, description]), error="", attempts=0)

    translated_chunks: list[str] = []
    attempts = 0
    errors: list[str] = []
    for idx, chunk in enumerate(chunk_text(description, max_chars=max_chunk_chars)):
        result = await adapter.translate(chunk, use_cache=use_cache)
        attempts += result.attempts
        if result.status == "ok" and result.text is not None:
            translated_chunks.append(result.text)
        else:
            translated_chunks.append(chunk)
            errors.append(f"chunk {idx}: {result.error}")
    translated_description = "".join(translated_chunks)
    return StrategyResult(
        value=separator.join([name, tags, translated_description]),
        error=merge_translation_errors(*errors),
        attempts=attempts,
    )
