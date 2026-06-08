from typing import Any

from datasets import Dataset, concatenate_datasets


Record = dict[str, Any]
RecordIndex = dict[int, Record]


def target_fields(rules: list[Any]) -> list[str]:
    return [str(rule.target or rule.source) for rule in rules]


def init_state(limit: int, fields: list[str]) -> RecordIndex:
    del limit, fields
    return {}


def apply_record(state: RecordIndex, record: Record, fields: list[str]) -> None:
    row_idx = int(record["row_idx"])
    if not all(field in record for field in fields):
        raise ValueError(f"record {row_idx} is missing required translated fields")
    state[row_idx] = dict(record)


def record_succeeded(record: Record, fields: list[str]) -> bool:
    if not all(field in record for field in fields):
        return False
    status = str(record.get("status", "ok")).strip().lower()
    return status not in {"error", "exception", "failed"}


def row_complete(state: RecordIndex, row_idx: int, fields: list[str]) -> bool:
    record = state.get(row_idx)
    if record is None:
        return False
    return all(field in record for field in fields)


def missing_rows(state: RecordIndex, limit: int, fields: list[str]) -> list[int]:
    return [idx for idx in range(limit) if not row_complete(state, idx, fields)]


def materialize_split(
    dataset: Dataset,
    limit: int,
    state: RecordIndex,
    fields: list[str],
    drop_columns: list[str],
    *,
    chunk_size: int,
) -> Dataset:
    if limit == 0:
        empty = dataset.select([])
        removable = [column for column in drop_columns if column in empty.column_names]
        if removable:
            empty = empty.remove_columns(removable)
        for field in fields:
            empty = empty.add_column(field, [])
        return empty

    chunks: list[Dataset] = []
    step = max(1, int(chunk_size))
    for start_idx in range(0, limit, step):
        end_idx = min(start_idx + step, limit)
        chunk = dataset.select(range(start_idx, end_idx))
        chunk_data = chunk.to_dict()
        for column in drop_columns:
            chunk_data.pop(column, None)
        for field in fields:
            chunk_data[field] = [state[row_idx][field] for row_idx in range(start_idx, end_idx)]
        chunks.append(Dataset.from_dict(chunk_data))
    return chunks[0] if len(chunks) == 1 else concatenate_datasets(chunks)
