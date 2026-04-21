from typing import Any
import re

from data_translate.adapters.translation_base import TranslationAdapter
from data_translate.domain.renderers import action_sequence
from data_translate.domain.translation_common import Options, StrategyResult, merge_translation_errors


ACTION_LINE_RE = re.compile(r"^[a-z_]+\(")


def validate_weblinx_query_input(value: Any, options: Options, *, field_name: str) -> str:
    del options
    if value is None or isinstance(value, (str, int, float, bool)):
        return ""
    return (
        f"field {field_name!r} with strategy 'weblinx_query' must be a scalar text-like value, "
        f"got {type(value).__name__}"
    )


def _split_records(query: str, *, user_prefix: str, agent_prefix: str) -> list[str]:
    if not query:
        return []

    records: list[str] = []
    current: list[str] = []
    for line in query.splitlines():
        if line.startswith(user_prefix) or line.startswith(agent_prefix) or ACTION_LINE_RE.match(line):
            if current:
                records.append("\n".join(current))
            current = [line]
        else:
            if current:
                current.append(line)
            else:
                current = [line]
    if current:
        records.append("\n".join(current))
    return records


def _extract_quoted_value(text: str, *, start_idx: int) -> tuple[str, int] | None:
    if start_idx >= len(text):
        return None
    quote = text[start_idx]
    if quote not in {'"', "'"}:
        return None

    # WebLINX occasionally stores quoted utterances as utterance=""..."".
    # Treat the inner quotes as content rather than an empty string payload.
    if start_idx + 1 < len(text) and text[start_idx + 1] == quote:
        value_chars = [quote]
        idx = start_idx + 2
        escaped = False
        while idx < len(text):
            char = text[idx]
            if escaped:
                value_chars.append(char)
                escaped = False
            elif char == "\\":
                value_chars.append(char)
                escaped = True
            elif char == quote and idx + 1 < len(text) and text[idx + 1] == quote:
                value_chars.append(char)
                return "".join(value_chars), idx + 1
            else:
                value_chars.append(char)
            idx += 1
        return None

    value_chars: list[str] = []
    idx = start_idx + 1
    escaped = False
    while idx < len(text):
        char = text[idx]
        if escaped:
            value_chars.append(char)
            escaped = False
        elif char == "\\":
            value_chars.append(char)
            escaped = True
        elif char == quote:
            return "".join(value_chars), idx
        else:
            value_chars.append(char)
        idx += 1
    return None


def _extract_agent_say_utterance(record: str, *, agent_prefix: str) -> tuple[str, str, str] | None:
    if not record.startswith(agent_prefix):
        return None

    action = record[len(agent_prefix) :]
    if not action.startswith("say("):
        return None

    utterance_key = "utterance="
    key_idx = action.find(utterance_key)
    if key_idx < 0:
        return None

    value_start_idx = key_idx + len(utterance_key)
    parsed = _extract_quoted_value(action, start_idx=value_start_idx)
    if parsed is None:
        return None

    utterance, value_end_idx = parsed
    prefix = f"{agent_prefix}{action[:value_start_idx + 1]}"
    suffix = action[value_end_idx:]
    return prefix, utterance, suffix


def _needs_translation(text: str) -> bool:
    return any(char.isalpha() for char in text)


async def _translate_preserving_blank_lines(
    text: str,
    *,
    line_idx: int,
    adapter: TranslationAdapter,
    use_cache: bool,
) -> tuple[str, int, str]:
    if not text.strip() or not _needs_translation(text):
        return text, 0, ""

    translated_parts: list[str] = []
    attempts = 0
    errors: list[str] = []
    parts = text.split("\n")
    idx = 0
    while idx < len(parts):
        if not parts[idx].strip():
            translated_parts.append(parts[idx])
            idx += 1
            continue

        end_idx = idx
        while end_idx < len(parts) and parts[end_idx].strip():
            end_idx += 1

        segment = "\n".join(parts[idx:end_idx])
        result = await adapter.translate(segment, use_cache=use_cache)
        attempts += result.attempts
        if result.status == "ok" and result.text is not None:
            translated_parts.extend(result.text.split("\n"))
        else:
            translated_parts.extend(parts[idx:end_idx])
            errors.append(f"line {line_idx}: {result.error}")
        idx = end_idx

    return "\n".join(translated_parts), attempts, merge_translation_errors(*errors)


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
    translated, attempts, error = await _translate_preserving_blank_lines(
        content,
        line_idx=line_idx,
        adapter=adapter,
        use_cache=use_cache,
    )
    if error:
        return line, attempts, error
    return f"{user_prefix}{translated}", attempts, ""


async def _translate_agent_say_record(
    record: str,
    *,
    line_idx: int,
    agent_prefix: str,
    adapter: TranslationAdapter,
    use_cache: bool,
) -> tuple[str, int, str]:
    parsed = _extract_agent_say_utterance(record, agent_prefix=agent_prefix)
    if parsed is None:
        return record, 0, ""

    prefix, utterance, suffix = parsed
    translated, attempts, error = await _translate_preserving_blank_lines(
        utterance,
        line_idx=line_idx,
        adapter=adapter,
        use_cache=use_cache,
    )
    if error:
        return record, attempts, error
    return f"{prefix}{translated}{suffix}", attempts, ""


async def translate_weblinx_query(value: Any, adapter: TranslationAdapter, options: Options, *, use_cache: bool) -> StrategyResult:
    query = str(value or "")
    translated_lines: list[str] = []
    attempts = 0
    errors: list[str] = []
    user_prefix = str(options.get("user_prefix", "User: "))
    agent_prefix = str(options.get("agent_prefix", "Agent: "))
    translate_agent_say_utterance = bool(options.get("translate_agent_say_utterance", False))

    for line_idx, line in enumerate(_split_records(query, user_prefix=user_prefix, agent_prefix=agent_prefix)):
        if line.startswith(user_prefix):
            translated_line, line_attempts, line_error = await _translate_user_line(
                line,
                line_idx=line_idx,
                user_prefix=user_prefix,
                adapter=adapter,
                use_cache=use_cache,
            )
        elif translate_agent_say_utterance:
            translated_line, line_attempts, line_error = await _translate_agent_say_record(
                line,
                line_idx=line_idx,
                agent_prefix=agent_prefix,
                adapter=adapter,
                use_cache=use_cache,
            )
        else:
            translated_line, line_attempts, line_error = line, 0, ""
        attempts += line_attempts
        if line_error:
            errors.append(line_error)
        translated_lines.append(translated_line)

    translated_query = "\n".join(translated_lines)
    if len(query.splitlines()) != len(translated_query.splitlines()):
        errors.append(f"line count changed: {len(query.splitlines())} -> {len(translated_query.splitlines())}")
    if action_sequence(query) != action_sequence(translated_query):
        errors.append("action sequence changed")
    return StrategyResult(translated_query, error=merge_translation_errors(*errors), attempts=attempts)
