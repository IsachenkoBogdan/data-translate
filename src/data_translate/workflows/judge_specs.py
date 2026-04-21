from collections.abc import Callable
from pathlib import Path

from datasets import load_dataset

from data_translate.adapters.llm_base import LLMChatAdapter
from data_translate.config.models_workflow import BenchmarkWorkflowConfigModel, EvaluateWorkflowConfigModel
from data_translate.domain.benchmark_records import (
    benchmark_done_key,
    build_benchmark_error_record,
    build_benchmark_tasks,
    make_benchmark_record_processor,
)
from data_translate.domain.benchmark_reporting import benchmark_summary
from data_translate.domain.benchmark_sampling import sample_benchmark_rows
from data_translate.domain.evaluation_records import (
    EvaluationTask,
    build_evaluation_error_record,
    build_evaluation_tasks,
    make_evaluation_record_processor,
)
from data_translate.domain.evaluation_reporting import evaluation_summary
from data_translate.domain.evaluation_sampling import sample_evaluation_rows
from data_translate.domain.preflight import validate_evaluation_inputs
from data_translate.engine.jsonl import load_jsonl
from data_translate.services.datasets import DATASET_RESOLVER
from data_translate.services.judges import build_translation_judge
from data_translate.workflows.judge_entrypoint import JudgeRunSpec



def _judge_context(config: EvaluateWorkflowConfigModel | BenchmarkWorkflowConfigModel) -> dict[str, object]:
    return {
        "artifacts": config.artifacts.model_dump(mode="python"),
        "runtime": config.runtime.model_dump(mode="python"),
        "llm": config.llm.model_dump(mode="python"),
        "prompt": config.prompt.model_dump(mode="python"),
    }



def _done_keys(records_path: str, *, with_model: bool) -> set[str] | set[tuple[str, str]]:
    rows = [row for row in load_jsonl(Path(records_path)) if str(row.get("status", "")).strip() == "ok"]
    if with_model:
        return {(str(row["model"]), str(row["sample_id"])) for row in rows}
    return {str(row["sample_id"]) for row in rows}



def _evaluation_task_done_key(task: EvaluationTask) -> str:
    return task[2]


def _evaluation_record_done_key(record: dict[str, object]) -> str:
    return str(record["sample_id"])



def _evaluation_summary_context(config: EvaluateWorkflowConfigModel) -> dict[str, object]:
    return {
        "workflow": config.meta.workflow,
        "dataset_id": config.meta.dataset_id,
        "run_name": config.meta.run_name,
        **_judge_context(config),
    }



def _benchmark_summary_context(config: BenchmarkWorkflowConfigModel) -> dict[str, object]:
    return {
        "workflow": config.meta.workflow,
        "run_name": config.meta.run_name,
        **_judge_context(config),
        "benchmark": config.benchmark.model_dump(mode="python"),
    }



def _benchmark_summary_builder(labels: list[str]) -> Callable[[list[dict[str, object]]], dict[str, object]]:
    return lambda rows: benchmark_summary(rows, labels)



def build_evaluate_judge_spec(config: EvaluateWorkflowConfigModel, adapter: LLMChatAdapter) -> JudgeRunSpec:
    evaluation = config.dataset.evaluation
    if evaluation is None:
        raise ValueError("evaluate workflow requires dataset.evaluation")

    input_paths = DATASET_RESOLVER.resolve_evaluation_input_paths(config)
    datasets = DATASET_RESOLVER.load_evaluation_inputs_from_paths(input_paths)
    validate_evaluation_inputs(config, datasets, input_paths)
    samples = sample_evaluation_rows(datasets, evaluation)
    done = _done_keys(config.artifacts.records_path, with_model=False)
    judge = build_translation_judge(adapter=adapter, runtime=config.runtime, llm=config.llm, prompt=config.prompt)
    tasks = build_evaluation_tasks(config, samples)
    process_item = make_evaluation_record_processor(
        config=config,
        datasets=datasets,
        resolved_paths={alias: str(path) for alias, path in input_paths.items()},
        judge=judge,
    )

    return JudgeRunSpec(
        tasks=tasks,
        done_keys=done,
        task_done_key=_evaluation_task_done_key,
        record_done_key=_evaluation_record_done_key,
        process_item=process_item,
        on_process_error=lambda task, exc: build_evaluation_error_record(config, task, exc),
        concurrency=config.runtime.concurrency,
        desc="evaluate",
        summary_builder=evaluation_summary,
        summary_context=_evaluation_summary_context(config),
        start_log={
            "dataset_id": config.meta.dataset_id,
            "run_name": config.meta.run_name,
            "model": config.llm.model,
        },
    )



def build_benchmark_judge_spec(config: BenchmarkWorkflowConfigModel, adapter: LLMChatAdapter) -> JudgeRunSpec:
    dataset = load_dataset(config.benchmark.dataset, config.benchmark.dataset_config, split=config.benchmark.split)
    samples = sample_benchmark_rows(dataset, config.benchmark)
    if not samples:
        raise RuntimeError("No samples selected. Check benchmark filters.")

    done = _done_keys(config.artifacts.records_path, with_model=True)
    judges = {
        model: build_translation_judge(
            adapter=adapter,
            runtime=config.runtime,
            llm=config.llm,
            prompt=config.prompt,
            model=model,
        )
        for model in config.benchmark.models
    }
    labels = [str(label) for label in config.benchmark.bin_labels]
    thresholds = [float(item) for item in config.benchmark.bin_thresholds_0_10]
    tasks = build_benchmark_tasks(config, samples)
    process_item = make_benchmark_record_processor(
        config=config,
        judges=judges,
        labels=labels,
        thresholds=thresholds,
    )

    return JudgeRunSpec(
        tasks=tasks,
        done_keys=done,
        task_done_key=lambda task: benchmark_done_key(config, task),
        record_done_key=lambda row: (str(row["model"]), str(row["sample_id"])),
        process_item=process_item,
        on_process_error=lambda task, exc: build_benchmark_error_record(config, task, exc),
        concurrency=config.runtime.concurrency,
        desc="benchmark-judge",
        summary_builder=_benchmark_summary_builder(labels),
        summary_context=_benchmark_summary_context(config),
        start_log={
            "run_name": config.meta.run_name,
            "models": config.benchmark.models,
        },
    )
