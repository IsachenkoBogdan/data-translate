import random
from collections import defaultdict
from typing import Any

from data_translate.config.models_dataset_evaluation import EvaluationSpecModel


RowSample = dict[str, Any]


def sample_evaluation_rows(datasets: dict[str, Any], evaluation: EvaluationSpecModel) -> list[RowSample]:
    sampling = evaluation.sampling
    dataset = datasets[sampling.dataset]
    split_names = list(dataset.keys()) if evaluation.split == "all" else [evaluation.split]
    rng = random.Random(evaluation.seed)

    if sampling.strategy == "per_split_random":
        samples = []
        for split_name in split_names:
            size = len(dataset[split_name])
            n_samples = min(sampling.samples_per_split, size) if sampling.samples_per_split > 0 else size
            for row_idx in sorted(rng.sample(range(size), n_samples)):
                samples.append({"split": split_name, "row_idx": row_idx, "group_value": "", "group_count": size})
        return samples

    by_split_value: dict[tuple[str, str], list[RowSample]] = defaultdict(list)
    counts: dict[str, int] = defaultdict(int)
    for split_name in split_names:
        values = dataset[split_name][sampling.field]
        for row_idx, raw_value in enumerate(values):
            value = str(raw_value)
            counts[value] += 1
            by_split_value[(split_name, value)].append(
                {"split": split_name, "row_idx": row_idx, "group_value": value, "group_count": 0}
            )

    samples = []
    for split_name, value in sorted(by_split_value):
        rows = by_split_value[(split_name, value)]
        for row in rng.sample(rows, min(sampling.samples_per_value, len(rows))):
            row["group_count"] = counts[value]
            samples.append(row)
    return sorted(samples, key=lambda item: (item["split"], item["group_value"], item["row_idx"]))
