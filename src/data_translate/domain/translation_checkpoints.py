from pathlib import Path
from typing import Any

from datasets import Dataset

from data_translate.domain.translation_state import RecordIndex, apply_record, init_state, record_succeeded, row_complete
from data_translate.engine.jsonl import load_jsonl, load_jsonl_index


def split_limit(dataset: Dataset, max_rows_per_split: int) -> int:
    return len(dataset) if max_rows_per_split <= 0 else min(len(dataset), max_rows_per_split)


def build_translate_records(checkpoint_dir: Path, splits: list[str]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for split in splits:
        split_records = list(load_jsonl_index(checkpoint_dir / f"{split}.jsonl", "row_idx").values())
        split_records.sort(key=lambda row: int(row["row_idx"]))
        for record in split_records:
            enriched = dict(record)
            enriched["split"] = split
            records.append(enriched)
    return records


def restore_state_from_checkpoint(
    *,
    checkpoint_path: Path,
    limit: int,
    fields: list[str],
) -> tuple[RecordIndex, dict[Any, dict[str, Any]]]:
    state = init_state(limit, fields)
    done = load_jsonl_index(checkpoint_path, "row_idx")
    for row_idx, record in done.items():
        if int(row_idx) < limit:
            if record_succeeded(record, fields):
                apply_record(state, record, fields)
    return state, done


def pending_rows_for_range(
    *,
    dataset: Dataset,
    state: RecordIndex,
    fields: list[str],
    start_idx: int,
    end_idx: int,
) -> list[tuple[int, Any]]:
    if all(row_complete(state, idx, fields) for idx in range(start_idx, end_idx)):
        return []
    return [
        (idx, dataset[idx])
        for idx in range(start_idx, end_idx)
        if not row_complete(state, idx, fields)
    ]
