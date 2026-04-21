from typing import Any


def join_sample_id(*parts: object) -> str:
    return ":".join(str(part) for part in parts)


def optional_value(row: dict[str, Any], column: str, default: Any = "") -> Any:
    if not column:
        return default
    return row.get(column, default)


def with_score_data(base: dict[str, Any], score_data: dict[str, Any]) -> dict[str, Any]:
    return {
        **base,
        **score_data,
    }
