from collections.abc import Mapping
from typing import Any
import re


GuardOptions = Mapping[str, Any]


def has_letters(value: Any) -> bool:
    return any(char.isalpha() for char in str(value or ""))


def _guard_specs(options: GuardOptions) -> list[Mapping[str, Any]]:
    raw = options.get("guards", options.get("skip_if", []))
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("translation guards must be a list")
    return [spec for spec in raw if isinstance(spec, Mapping)]


def should_skip_translation(value: Any, options: GuardOptions) -> bool:
    text = str(value or "")
    for spec in _guard_specs(options):
        kind = str(spec.get("kind", ""))
        if kind == "no_letters":
            if not has_letters(text):
                return True
        elif kind == "fullmatch_regex":
            pattern = str(spec.get("pattern", ""))
            if pattern and re.fullmatch(pattern, text):
                return True
        else:
            raise ValueError(f"unknown translation guard: {kind}")
    return False
