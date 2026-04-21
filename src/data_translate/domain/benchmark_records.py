from collections.abc import Callable
from typing import Any

from data_translate.config.models_workflow import BenchmarkWorkflowConfigModel
from data_translate.domain.judging import TranslationJudge
from data_translate.domain.judge_records_common import join_sample_id, optional_value, with_score_data
from data_translate.domain.languages import extract_language_pair, language_names
from data_translate.domain.scoring import bin_score


BenchmarkTask = tuple[str, dict[str, Any]]


def _format_exception(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:300]}"


def build_benchmark_error_record(
    config: BenchmarkWorkflowConfigModel,
    task: BenchmarkTask,
    exc: BaseException,
) -> dict[str, Any]:
    model, row = task
    dataset_idx = int(row.get("_dataset_idx", -1))
    sample_id = join_sample_id(config.benchmark.dataset, config.benchmark.split, dataset_idx)
    return {
        "sample_id": sample_id,
        "dataset": config.benchmark.dataset,
        "split": config.benchmark.split,
        "dataset_idx": dataset_idx,
        "model": model,
        "lp": str(row.get("_lp", "")),
        "source_dataset": "",
        "domain": "",
        "year": None,
        "system": "",
        "source_text": "",
        "translation": "",
        "reference": "",
        "human_score_raw": None,
        "human_bin": None,
        "llm_bin": None,
        "llm_score": None,
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


def build_benchmark_tasks(config: BenchmarkWorkflowConfigModel, samples: list[dict[str, Any]]) -> list[BenchmarkTask]:
    return [(model, row) for model in config.benchmark.models for row in samples]


def benchmark_done_key(config: BenchmarkWorkflowConfigModel, task: BenchmarkTask) -> tuple[str, str]:
    model, row = task
    sample_id = join_sample_id(config.benchmark.dataset, config.benchmark.split, int(row["_dataset_idx"]))
    return model, sample_id


def make_benchmark_record_processor(
    *,
    config: BenchmarkWorkflowConfigModel,
    judges: dict[str, TranslationJudge],
    labels: list[str],
    thresholds: list[float],
) -> Callable[[BenchmarkTask], Any]:
    async def process_item(task: BenchmarkTask) -> dict[str, Any]:
        model, row = task
        dataset_idx = int(row["_dataset_idx"])
        lp = str(row.get("_lp") or extract_language_pair(str(optional_value(row, config.benchmark.language_pair_column, ""))))
        sample_id = join_sample_id(config.benchmark.dataset, config.benchmark.split, dataset_idx)
        source_lang, target_lang = language_names(lp)
        source_text = str(row.get(config.benchmark.source_column, ""))
        translation_text = str(row.get(config.benchmark.translation_column, ""))
        reference_text = str(optional_value(row, config.benchmark.reference_column, ""))
        raw_human_score = float(row[config.benchmark.human_score_column])
        human_bin = bin_score(raw_human_score, thresholds, labels)
        score_data = await judges[model].score(
            source_text=source_text,
            translation_text=translation_text,
            source_lang=source_lang,
            target_lang=target_lang,
            domain=str(optional_value(row, config.benchmark.domain_column, "general")),
            reference_text=reference_text,
            score_key="llm_score",
        )
        llm_bin = bin_score(float(score_data["llm_score"]), thresholds, labels) if score_data["llm_score"] is not None else None
        return with_score_data({
            "sample_id": sample_id,
            "dataset": config.benchmark.dataset,
            "split": config.benchmark.split,
            "dataset_idx": dataset_idx,
            "model": model,
            "lp": lp,
            "source_dataset": optional_value(row, config.benchmark.language_pair_column, ""),
            "domain": optional_value(row, config.benchmark.domain_column, ""),
            "year": optional_value(row, config.benchmark.year_column, None),
            "system": optional_value(row, config.benchmark.system_column, ""),
            "source_text": source_text,
            "translation": translation_text,
            "reference": reference_text,
            "human_score_raw": raw_human_score,
            "human_bin": human_bin,
            "llm_bin": llm_bin,
        }, score_data)

    return process_item
