from collections import defaultdict
from typing import Any

from scipy.stats import pearsonr, spearmanr
from sklearn.metrics import cohen_kappa_score

from data_translate.domain.reporting_common import finite, mean, rounded, status_counts
from data_translate.domain.usage_reporting import usage_summary


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    statistic = float(pearsonr(xs, ys).statistic)
    return finite(statistic)


def spearman(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    statistic = float(spearmanr(xs, ys).statistic)
    return finite(statistic)


def cohen_kappa(human_bins: list[str], llm_bins: list[str], labels: list[str], *, weights: str | None = None) -> float | None:
    if len(human_bins) != len(llm_bins) or not human_bins:
        return None
    score = float(cohen_kappa_score(human_bins, llm_bins, labels=labels, weights=weights))
    return finite(score)


def benchmark_stats(rows: list[dict[str, Any]], labels: list[str]) -> dict[str, Any]:
    human_scores = [float(row["human_score_0_10"]) for row in rows]
    llm_scores = [float(row["llm_score"]) for row in rows]
    human_bins = [str(row["human_bin"]) for row in rows]
    llm_bins = [str(row["llm_bin"]) for row in rows]
    return {
        "n": len(rows),
        "mean_human_score_0_10": rounded(mean(human_scores)),
        "mean_llm_score": rounded(mean(llm_scores)),
        "pearson": rounded(pearson(human_scores, llm_scores)),
        "spearman": rounded(spearman(human_scores, llm_scores)),
        "cohen_kappa": rounded(cohen_kappa(human_bins, llm_bins, labels)),
        "quadratic_weighted_kappa": rounded(cohen_kappa(human_bins, llm_bins, labels, weights="quadratic")),
        "usage": usage_summary(rows),
    }


def benchmark_summary(rows: list[dict[str, Any]], labels: list[str]) -> dict[str, Any]:
    by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_model[str(row["model"])].append(row)

    model_stats = {}
    for model, model_rows in sorted(by_model.items()):
        ok_rows = [row for row in model_rows if row.get("status") == "ok" and row.get("llm_score") is not None]
        by_lp: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in ok_rows:
            by_lp[str(row.get("lp", ""))].append(row)
        stats = benchmark_stats(ok_rows, labels)
        model_stats[model] = {
            "rows": len(model_rows),
            "ok_rows": len(ok_rows),
            "status_counts": status_counts(model_rows),
            **{key: value for key, value in stats.items() if key != "n"},
            "by_language_pair": {lp: benchmark_stats(lp_rows, labels) for lp, lp_rows in sorted(by_lp.items())},
        }

    return {
        "rows": len(rows),
        "usage": usage_summary(rows),
        "models": model_stats,
        "notes": [
            "Human scores are normalized to 0-10 before correlations and binning.",
            "Cohen's kappa uses discrete bins from bin_thresholds_0_10; also report Spearman/Pearson because MT human scores are numeric.",
        ],
    }
