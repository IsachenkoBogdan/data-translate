from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any, TypeVar

from data_translate.engine.execution import process_jsonl_records
from data_translate.engine.jsonl import load_jsonl, write_jsonl
from data_translate.engine.reports import write_json_report


Task = TypeVar("Task")
Record = dict[str, Any]
SummaryBuilder = Callable[[list[Record]], dict[str, Any]]
DoneKey = str | tuple[str, str]


def _canonicalize_rows(
    rows: list[Record],
    record_done_key: Callable[[Record], DoneKey],
) -> list[Record]:
    latest_by_key: dict[DoneKey, tuple[int, Record]] = {}
    for idx, row in enumerate(rows):
        latest_by_key[record_done_key(row)] = (idx, row)
    return [row for _idx, row in sorted(latest_by_key.values(), key=lambda item: item[0])]


async def run_judge_records(
    *,
    records_path: Path,
    summary_path: Path,
    tasks: Iterable[Task],
    done_keys: set[DoneKey],
    task_done_key: Callable[[Task], DoneKey],
    record_done_key: Callable[[Record], DoneKey],
    process_item: Callable[[Task], Awaitable[Record]],
    on_process_error: Callable[[Task, BaseException], Record] | None,
    concurrency: int,
    desc: str,
    summary_builder: SummaryBuilder,
    summary_context: dict[str, Any],
) -> tuple[list[Record], dict[str, Any]]:
    await process_jsonl_records(
        output_path=records_path,
        tasks=tasks,
        is_done=lambda task: task_done_key(task) in done_keys,
        process_item=process_item,
        on_process_error=on_process_error,
        concurrency=concurrency,
        desc=desc,
        collect_records=False,
    )
    rows = _canonicalize_rows(load_jsonl(records_path), record_done_key)
    write_jsonl(records_path, rows)
    summary = {
        **summary_builder(rows),
        **summary_context,
    }
    write_json_report(summary_path, summary)
    return rows, summary
