from collections import Counter
import math
from statistics import fmean
from typing import Any


def rounded(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def mean(values: list[float]) -> float | None:
    return fmean(values) if values else None


def finite(value: float) -> float | None:
    return value if math.isfinite(value) else None


def float_value(row: dict[str, Any], key: str) -> float | None:
    value = row.get(key)
    return float(value) if isinstance(value, int | float) else None


def score_stats(values: list[int]) -> dict[str, Any]:
    return {
        "n": len(values),
        "mean_score": round(sum(values) / len(values), 3) if values else None,
        "min_score": min(values) if values else None,
        "max_score": max(values) if values else None,
    }


def status_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return dict(sorted(Counter(str(row.get("status")) for row in rows).items()))
