from pathlib import Path
from typing import Any

import jsonlines


Record = dict[str, Any]


def write_jsonl(path: Path, records: list[Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with jsonlines.open(path, mode="w", flush=True) as writer:
        for record in records:
            writer.write(record)


def append_jsonl(path: Path, records: list[Record]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with jsonlines.open(path, mode="a", flush=True) as writer:
        for record in records:
            writer.write(record)


def load_jsonl(path: Path) -> list[Record]:
    if not path.exists():
        return []
    with jsonlines.open(path, mode="r") as reader:
        return [dict(row) for row in reader]


def load_jsonl_index(path: Path, key: str) -> dict[Any, Record]:
    return {record[key]: record for record in load_jsonl(path)}
