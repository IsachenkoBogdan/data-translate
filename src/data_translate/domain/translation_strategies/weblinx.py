from typing import Any

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.domain.renderers import action_sequence
from data_translate.domain.translation_common import Options, StrategyResult, merge_translation_errors


def validate_weblinx_query_input(value: Any, options: Options, *, field_name: str) -> str:
    del options
    if value is None or isinstance(value, (str, int, float, bool)):
        return ""
    return (
        f"field {field_name!r} with strategy 'weblinx_query' must be a scalar text-like value, "
        f"got {type(value).__name__}"
    )


async def _translate_user_line(
    line: str,
    *,
    line_idx: int,
    user_prefix: str,
    adapter: TranslationAdapter,
    use_cache: bool,
) -> tuple[str, int, str]:
    if not line.startswith(user_prefix):
        return line, 0, ""

    content = line[len(user_prefix) :]
    result = await adapter.translate(content, use_cache=use_cache)
    if result.status == "ok" and result.text is not None:
        return f"{user_prefix}{result.text}", result.attempts, ""
    return line, result.attempts, f"line {line_idx}: {result.error}"


async def translate_weblinx_query(value: Any, adapter: TranslationAdapter, options: Options, *, use_cache: bool) -> StrategyResult:
    if bool(options.get("translate_agent_say_utterance", False)):
        raise NotImplementedError(
            "translate_agent_say_utterance=true is intentionally not implemented. "
            "Current rules keep Agent actions unchanged, following the RU reference."
        )

    query = str(value or "")
    lines = query.splitlines()
    translated_lines: list[str] = []
    attempts = 0
    errors: list[str] = []
    user_prefix = str(options.get("user_prefix", "User: "))

    for line_idx, line in enumerate(lines):
        translated_line, line_attempts, line_error = await _translate_user_line(
            line,
            line_idx=line_idx,
            user_prefix=user_prefix,
            adapter=adapter,
            use_cache=use_cache,
        )
        attempts += line_attempts
        if line_error:
            errors.append(line_error)
        translated_lines.append(translated_line)

    translated_query = "\n".join(translated_lines)
    if len(lines) != len(translated_lines):
        errors.append(f"line count changed: {len(lines)} -> {len(translated_lines)}")
    if action_sequence(query) != action_sequence(translated_query):
        errors.append("action sequence changed")
    return StrategyResult(translated_query, error=merge_translation_errors(*errors), attempts=attempts)
