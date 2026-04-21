from collections.abc import Callable
from typing import Any

from datasets import DatasetDict

from data_translate.config.models_workflow import EvaluateWorkflowConfigModel
from data_translate.domain.judging import TranslationJudge
from data_translate.domain.judge_records_common import join_sample_id, with_score_data
from data_translate.domain.renderers import render_value


EvaluationTask = tuple[dict[str, Any], Any, str]


def _format_exception(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:300]}"


def build_evaluation_error_record(
    config: EvaluateWorkflowConfigModel,
    task: EvaluationTask,
    exc: BaseException,
) -> dict[str, Any]:
    sample, field_pair, sample_id = task
    return {
        "sample_id": sample_id,
        "split": sample["split"],
        "row_idx": sample["row_idx"],
        "field": field_pair.name or field_pair.translation_field,
        "source_dataset": field_pair.source_dataset,
        "source_field": field_pair.source_field,
        "translation_dataset": field_pair.translation_dataset,
        "translation_field": field_pair.translation_field,
        "sample_group_value": sample["group_value"],
        "sample_group_count": sample["group_count"],
        "dataset_id": config.meta.dataset_id,
        "dataset_raw_path": "",
        "dataset_translated_path": "",
        "model": config.llm.model,
        "source_text": "",
        "translation": "",
        "score": None,
        "comment": "",
        "status": "error",
        "parse_status": "exception",
        "raw_response": "",
        "attempts": 0,
        "error": _format_exception(exc),
        "usage": {},
        "usage_prompt_tokens": None,
        "usage_completion_tokens": None,
        "usage_total_tokens": None,
        "usage_cost": None,
        "finish_reason": "",
        "rate_limit_waits": 0,
        "rate_limit_wait_seconds": 0.0,
    }



def build_evaluation_tasks(config: EvaluateWorkflowConfigModel, samples: list[dict[str, Any]]) -> list[EvaluationTask]:
    evaluation = config.dataset.evaluation
    if evaluation is None:
        raise ValueError("evaluate workflow requires dataset.evaluation")
    tasks: list[EvaluationTask] = []
    for sample in samples:
        for field_pair in evaluation.field_pairs:
            field_name = field_pair.name or field_pair.translation_field
            sample_id = join_sample_id(sample["split"], sample["row_idx"], field_name)
            tasks.append((sample, field_pair, sample_id))
    return tasks



def make_evaluation_record_processor(
    *,
    config: EvaluateWorkflowConfigModel,
    datasets: dict[str, DatasetDict],
    resolved_paths: dict[str, str],
    judge: TranslationJudge,
) -> Callable[[EvaluationTask], Any]:
    evaluation = config.dataset.evaluation
    if evaluation is None:
        raise ValueError("evaluate workflow requires dataset.evaluation")

    async def process_item(task: EvaluationTask) -> dict[str, Any]:
        sample, field_pair, sample_id = task
        source_dataset = datasets[field_pair.source_dataset]
        translation_dataset = datasets[field_pair.translation_dataset]
        source_row = source_dataset[sample["split"]][sample["row_idx"]]
        translation_row = translation_dataset[sample["split"]][sample["row_idx"]]
        source_text = render_value(source_row[field_pair.source_field], field_pair.source_format)
        translation_text = render_value(translation_row[field_pair.translation_field], field_pair.translation_format)
        score_data = await judge.score(
            source_text=source_text,
            translation_text=translation_text,
            source_lang=evaluation.source_lang,
            target_lang=evaluation.target_lang,
            domain=evaluation.domain,
        )
        return with_score_data({
            "sample_id": sample_id,
            "split": sample["split"],
            "row_idx": sample["row_idx"],
            "field": field_pair.name or field_pair.translation_field,
            "source_dataset": field_pair.source_dataset,
            "source_field": field_pair.source_field,
            "translation_dataset": field_pair.translation_dataset,
            "translation_field": field_pair.translation_field,
            "sample_group_value": sample["group_value"],
            "sample_group_count": sample["group_count"],
            "dataset_id": config.meta.dataset_id,
            "dataset_raw_path": resolved_paths.get(field_pair.source_dataset, config.dataset.artifacts.raw_path),
            "dataset_translated_path": resolved_paths.get(field_pair.translation_dataset, ""),
            "model": config.llm.model,
            "source_text": source_text,
            "translation": translation_text,
        }, score_data)

    return process_item
