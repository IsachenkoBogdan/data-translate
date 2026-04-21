from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio
import structlog

from data_translate.config.models_workflow import BenchmarkWorkflowConfigModel, EvaluateWorkflowConfigModel
from data_translate.engine.judge_run import DoneKey, Record, SummaryBuilder, Task, run_judge_records
from data_translate.services.judges import build_llm_adapter


JudgeWorkflowConfig = EvaluateWorkflowConfigModel | BenchmarkWorkflowConfigModel


@dataclass(frozen=True)
class JudgeRunSpec:
    tasks: Iterable[Task]
    done_keys: set[DoneKey]
    task_done_key: Callable[[Task], DoneKey]
    record_done_key: Callable[[Record], DoneKey]
    process_item: Callable[[Task], Awaitable[Record]]
    on_process_error: Callable[[Task, BaseException], Record] | None
    concurrency: int
    desc: str
    summary_builder: SummaryBuilder
    summary_context: dict[str, Any]
    start_log: dict[str, Any]


SpecFactory = Callable[[JudgeWorkflowConfig, Any], JudgeRunSpec]


async def _run(config: JudgeWorkflowConfig, logger: structlog.stdlib.BoundLogger, spec_factory: SpecFactory) -> dict[str, Any]:
    adapter = build_llm_adapter(config.runtime, config.llm)
    try:
        spec = spec_factory(config, adapter)
        logger.info(f"{config.meta.workflow}.start", **spec.start_log)
        rows, summary = await run_judge_records(
            records_path=Path(config.artifacts.records_path),
            summary_path=Path(config.artifacts.summary_path),
            tasks=spec.tasks,
            done_keys=spec.done_keys,
            task_done_key=spec.task_done_key,
            record_done_key=spec.record_done_key,
            process_item=spec.process_item,
            on_process_error=spec.on_process_error,
            concurrency=spec.concurrency,
            desc=spec.desc,
            summary_builder=spec.summary_builder,
            summary_context=spec.summary_context,
        )
        logger.info(f"{config.meta.workflow}.done", rows=len(rows), **spec.start_log)
        return summary
    finally:
        await adapter.close()


def run_judge_entrypoint(
    *,
    config: JudgeWorkflowConfig,
    logger: structlog.stdlib.BoundLogger,
    spec_factory: SpecFactory,
) -> None:
    anyio.run(_run, config, logger, spec_factory)
