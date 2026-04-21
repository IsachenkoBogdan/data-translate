import random
from dataclasses import dataclass
from collections import defaultdict
from typing import Any

from data_translate.config.models_workflow_benchmark import BenchmarkSpecModel
from data_translate.domain.languages import extract_language_pair
from data_translate.domain.scoring import bin_score


RowSample = dict[str, Any]


@dataclass(frozen=True)
class BenchmarkFilters:
    language_pairs: frozenset[str]
    domains: frozenset[str]
    years: frozenset[int]


def build_benchmark_filters(benchmark: BenchmarkSpecModel) -> BenchmarkFilters:
    return BenchmarkFilters(
        language_pairs=frozenset(benchmark.language_pairs),
        domains=frozenset(benchmark.domains),
        years=frozenset(int(item) for item in benchmark.years),
    )


def row_allowed_for_benchmark(
    row: dict[str, Any],
    benchmark: BenchmarkSpecModel,
    *,
    filters: BenchmarkFilters,
) -> bool:
    lp = extract_language_pair(str(row.get(benchmark.language_pair_column, "")))
    domain = str(row.get(benchmark.domain_column, "")) if benchmark.domain_column else ""
    year = row.get(benchmark.year_column, None) if benchmark.year_column else None
    source_text = str(row.get(benchmark.source_column, ""))
    translation_text = str(row.get(benchmark.translation_column, ""))

    if filters.language_pairs and lp not in filters.language_pairs:
        return False
    if filters.domains and domain not in filters.domains:
        return False
    if filters.years and (year is None or int(year) not in filters.years):
        return False
    if benchmark.max_source_chars and len(source_text) > benchmark.max_source_chars:
        return False
    if benchmark.max_translation_chars and len(translation_text) > benchmark.max_translation_chars:
        return False
    return source_text.strip() != "" and translation_text.strip() != ""


def _annotate_candidate(
    row: dict[str, Any],
    *,
    dataset_idx: int,
    lp: str,
    benchmark: BenchmarkSpecModel,
    score_thresholds: list[float],
) -> dict[str, Any]:
    candidate = dict(row)
    candidate["_dataset_idx"] = dataset_idx
    candidate["_lp"] = lp
    if score_thresholds:
        raw_score = float(candidate[benchmark.human_score_column])
        candidate["_score_bin"] = bin_score(raw_score, score_thresholds)
    return candidate


def _round_robin_sample(groups: dict[str, list[dict[str, Any]]], sample_size: int, rng: random.Random) -> list[dict[str, Any]]:
    pools: list[list[dict[str, Any]]] = []
    for key in sorted(groups):
        rows = list(groups[key])
        rng.shuffle(rows)
        if rows:
            pools.append(rows)

    samples: list[dict[str, Any]] = []
    while len(samples) < sample_size:
        progressed = False
        for rows in pools:
            if not rows or len(samples) >= sample_size:
                continue
            samples.append(rows.pop())
            progressed = True
        if not progressed:
            break
    return samples


def _sample_language_pair_rows(
    rows: list[RowSample],
    *,
    sample_size: int,
    score_thresholds: list[float],
    rng: random.Random,
) -> list[RowSample]:
    n = min(sample_size, len(rows))
    if not score_thresholds:
        return rng.sample(rows, n)

    by_bin: dict[str, list[RowSample]] = defaultdict(list)
    for row in rows:
        by_bin[str(row["_score_bin"])].append(row)
    return _round_robin_sample(by_bin, n, rng)


def _sample_total_rows(
    all_rows: list[RowSample],
    *,
    sample_size: int,
    score_thresholds: list[float],
    rng: random.Random,
) -> list[RowSample]:
    n = min(sample_size, len(all_rows))
    if not score_thresholds:
        return rng.sample(all_rows, n)

    by_group: dict[str, list[RowSample]] = defaultdict(list)
    for row in all_rows:
        key = f"{row['_lp']}::{row['_score_bin']}"
        by_group[key].append(row)
    return _round_robin_sample(by_group, n, rng)


def sample_benchmark_rows(dataset: Any, benchmark: BenchmarkSpecModel) -> list[RowSample]:
    candidates_by_lp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    score_thresholds = [float(item) for item in benchmark.sampling_score_thresholds]
    filters = build_benchmark_filters(benchmark)
    for idx, row in enumerate(dataset):
        row = dict(row)
        if not row_allowed_for_benchmark(row, benchmark, filters=filters):
            continue
        lp = extract_language_pair(str(row.get(benchmark.language_pair_column, "")))
        candidates_by_lp[lp].append(
            _annotate_candidate(
                row,
                dataset_idx=idx,
                lp=lp,
                benchmark=benchmark,
                score_thresholds=score_thresholds,
            )
        )

    rng = random.Random(benchmark.seed)
    if benchmark.sample_size_per_language_pair > 0:
        samples = []
        for lp in sorted(candidates_by_lp):
            samples.extend(
                _sample_language_pair_rows(
                    candidates_by_lp[lp],
                    sample_size=benchmark.sample_size_per_language_pair,
                    score_thresholds=score_thresholds,
                    rng=rng,
                )
            )
    elif benchmark.sample_size_total > 0:
        all_rows = [row for rows in candidates_by_lp.values() for row in rows]
        samples = _sample_total_rows(
            all_rows,
            sample_size=benchmark.sample_size_total,
            score_thresholds=score_thresholds,
            rng=rng,
        )
    else:
        samples = [row for rows in candidates_by_lp.values() for row in rows]

    return sorted(samples, key=lambda item: (str(item.get("_lp", "")), int(item["_dataset_idx"])))
