from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import TypeVar

import anyio
import jsonlines
from tqdm import tqdm


T = TypeVar("T")
Record = dict[str, object]
ErrorRecordFactory = Callable[[T, BaseException], Record]


async def process_jsonl_records(
    *,
    output_path: Path,
    tasks: Iterable[T],
    is_done: Callable[[T], bool],
    process_item: Callable[[T], Awaitable[Record]],
    concurrency: int,
    desc: str,
    collect_records: bool = True,
    on_process_error: ErrorRecordFactory[T] | None = None,
) -> list[Record]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    task_send, task_receive = anyio.create_memory_object_stream[T](max_buffer_size=max(1, int(concurrency) * 2))
    record_send, record_receive = anyio.create_memory_object_stream[Record](max_buffer_size=max(1, int(concurrency) * 2))
    progress = tqdm(desc=desc)
    written_records: list[Record] = []

    async def enqueue_tasks() -> None:
        async with task_send:
            for task in tasks:
                if is_done(task):
                    continue
                await task_send.send(task)

    async def worker() -> None:
        async with task_receive.clone() as worker_receive, record_send.clone() as worker_send:
            async for task in worker_receive:
                try:
                    record = await process_item(task)
                except Exception as exc:
                    if on_process_error is None:
                        raise
                    record = on_process_error(task, exc)
                await worker_send.send(record)

    async def produce_records() -> None:
        async with record_send:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(enqueue_tasks)
                for _ in range(max(1, int(concurrency))):
                    task_group.start_soon(worker)

    try:
        with jsonlines.open(output_path, mode="a", flush=True) as writer:
            async with anyio.create_task_group() as task_group:
                task_group.start_soon(produce_records)
                async with record_receive:
                    async for record in record_receive:
                        writer.write(record)
                        if collect_records:
                            written_records.append(record)
                        progress.update(1)
    finally:
        progress.close()
    return written_records
