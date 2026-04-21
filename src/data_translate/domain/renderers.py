import re
from typing import Any, Literal, cast


ValueFormat = Literal["text", "text_list", "dialog_turns", "raw"]


ACTION_RE = re.compile(r"\b(?:say|click|load|text_input|scroll|change|paste|copy|tabcreate|tabswitch)\(")


def _scalar_text(value: Any) -> str:
    return "" if value is None else str(value)


def dialog_turns(value: Any) -> str:
    if not isinstance(value, list):
        return _scalar_text(value)
    parts: list[str] = []
    for turn in value:
        if isinstance(turn, dict):
            parts.append(f"{_scalar_text(turn.get('role', ''))}: {_scalar_text(turn.get('content', ''))}")
        else:
            parts.append(_scalar_text(turn))
    return "\n".join(parts)


def numbered_list(value: Any) -> str:
    if not isinstance(value, list):
        return _scalar_text(value)
    return "\n".join(f"{idx + 1}. {_scalar_text(item)}" for idx, item in enumerate(value))


FORMATTERS: dict[ValueFormat, Any] = {
    "text": _scalar_text,
    "text_list": numbered_list,
    "dialog_turns": dialog_turns,
    "raw": _scalar_text,
}


def render_value(value: Any, formatter: str) -> str:
    key = cast(ValueFormat, formatter)
    if key not in FORMATTERS:
        raise ValueError(f"unknown formatter: {formatter}")
    return FORMATTERS[key](value)


def action_sequence(text: str) -> list[str]:
    return ACTION_RE.findall(text)
