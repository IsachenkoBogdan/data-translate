import math


def normalize_score(score: float, min_score: float, max_score: float, higher_is_better: bool, *, scale: float = 10.0) -> float:
    if math.isclose(max_score, min_score):
        raise ValueError("human_score_min and human_score_max must be different")
    value = (score - min_score) / (max_score - min_score)
    value = max(0.0, min(1.0, value))
    if not higher_is_better:
        value = 1.0 - value
    return value * scale


def bin_score(value_0_10: float | None, thresholds: list[float], labels: list[str] | None = None) -> str | None:
    if value_0_10 is None:
        return None
    if labels is not None and len(labels) != len(thresholds) + 1:
        raise ValueError("labels must contain len(thresholds) + 1 items")
    for idx, threshold in enumerate(thresholds):
        if value_0_10 < float(threshold):
            return labels[idx] if labels is not None else f"bin_{idx}"
    return labels[-1] if labels is not None else f"bin_{len(thresholds)}"
