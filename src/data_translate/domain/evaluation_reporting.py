from collections import defaultdict
from typing import Any

from data_translate.domain.reporting_common import score_stats, status_counts
from data_translate.domain.usage_reporting import usage_summary


def evaluation_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_field: dict[str, list[int]] = defaultdict(list)
    by_split: dict[str, list[int]] = defaultdict(list)
    by_group: dict[str, list[int]] = defaultdict(list)
    group_dataset_counts: dict[str, int] = {}

    for row in rows:
        if row.get("score") is None:
            continue
        score = int(row["score"])
        by_field[str(row["field"])].append(score)
        by_split[str(row["split"])].append(score)
        group_value = str(row.get("sample_group_value", ""))
        if group_value:
            by_group[group_value].append(score)
            group_dataset_counts[group_value] = int(row.get("sample_group_count", 0))

    all_scores = [int(row["score"]) for row in rows if row.get("score") is not None]
    by_group_stats = {
        group: {**score_stats(values), "dataset_n": group_dataset_counts.get(group, 0)}
        for group, values in sorted(by_group.items())
    }
    balanced_scores = [group_stats["mean_score"] for group_stats in by_group_stats.values() if group_stats["mean_score"] is not None]
    weighted_sum = sum(
        group_stats["mean_score"] * group_stats["dataset_n"]
        for group_stats in by_group_stats.values()
        if group_stats["mean_score"] is not None and group_stats["dataset_n"]
    )
    total_group_n = sum(group_stats["dataset_n"] for group_stats in by_group_stats.values())
    return {
        "rows": len(rows),
        "status_counts": status_counts(rows),
        "overall": score_stats(all_scores),
        "usage": usage_summary(rows),
        "balanced_mean_score": round(sum(balanced_scores) / len(balanced_scores), 3) if balanced_scores else None,
        "dataset_weighted_mean_score": round(weighted_sum / total_group_n, 3) if total_group_n else None,
        "by_field": {field: score_stats(values) for field, values in sorted(by_field.items())},
        "by_split": {split: score_stats(values) for split, values in sorted(by_split.items())},
        "by_group": by_group_stats,
    }
