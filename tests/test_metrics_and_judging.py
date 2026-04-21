from pathlib import Path

import anyio
import pytest
from datasets import Dataset, DatasetDict

from data_translate.adapters.llm_response import LLMResponse, error_response, extract_finish_reason, extract_usage, success_response
from data_translate.config.loader import load_workflow_model
from data_translate.config.models_workflow_benchmark import BenchmarkSpecModel
from data_translate.domain.benchmark_reporting import benchmark_summary
from data_translate.domain.benchmark_sampling import build_benchmark_filters, row_allowed_for_benchmark, sample_benchmark_rows
from data_translate.domain.evaluation_reporting import evaluation_summary
from data_translate.domain.evaluation_sampling import sample_evaluation_rows
from data_translate.domain.judge_records_common import join_sample_id, optional_value, with_score_data
from data_translate.domain.judging import TranslationJudge, clamp_score, parse_score_response
from data_translate.domain.reporting_common import finite, float_value, mean, rounded, score_stats, status_counts
from data_translate.domain.scoring import bin_score, normalize_score
from data_translate.domain.usage_reporting import usage_summary
from data_translate.engine.reports import write_json_report


class FakeJudgeAdapter:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response
        self.calls: list[dict[str, object]] = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    async def close(self) -> None:
        return None


def test_scoring_and_reporting_helpers() -> None:
    assert normalize_score(75, 0, 100, True) == 7.5
    assert normalize_score(75, 0, 100, False) == 2.5
    assert normalize_score(75, 0, 100, True, scale=100.0) == 75.0
    assert bin_score(7.5, [6.0, 8.0], ["bad", "ok", "good"]) == "ok"
    assert bin_score(None, [6.0]) is None
    with pytest.raises(ValueError, match="different"):
        normalize_score(5, 1, 1, True)
    with pytest.raises(ValueError, match="labels must contain"):
        bin_score(3.0, [1.0], ["only"])

    assert rounded(1.23456) == 1.2346
    assert mean([1.0, 2.0]) == 1.5
    assert mean([]) is None
    assert finite(float("inf")) is None
    assert float_value({"x": 3}, "x") == 3.0
    assert float_value({"x": "3"}, "x") is None
    assert score_stats([2, 4]) == {"n": 2, "mean_score": 3.0, "min_score": 2, "max_score": 4}
    assert status_counts([{"status": "ok"}, {"status": "error"}, {}]) == {"None": 1, "error": 1, "ok": 1}


def test_usage_summary_and_judge_record_helpers() -> None:
    rows = [
        {
            "usage_prompt_tokens": 10,
            "usage_completion_tokens": 5,
            "usage_total_tokens": 15,
            "usage_cost": 0.2,
            "rate_limit_waits": 1,
            "rate_limit_wait_seconds": 0.5,
            "attempts": 2,
        }
    ]
    summary = usage_summary(rows)
    assert summary["request_count"] == 1
    assert summary["prompt_tokens"] == 10
    assert summary["retry_count"] == 1
    assert join_sample_id("test", 1, "field") == "test:1:field"
    assert optional_value({"x": 1}, "", "fallback") == "fallback"
    assert with_score_data({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_evaluation_sampling_and_reporting() -> None:
    config = load_workflow_model("evaluate", dataset_id="faithdial")
    evaluation = config.dataset.evaluation
    assert evaluation is not None
    datasets = {
        "source": DatasetDict(
            {
                "test": Dataset.from_dict({"history": [["h1"], ["h2"]], "knowledge": ["k1", "k2"]}),
            }
        )
    }
    per_split = sample_evaluation_rows(datasets, evaluation)
    assert all(item["split"] == "test" for item in per_split)

    stratified = evaluation.model_validate(
        {
            **evaluation.model_dump(mode="python"),
            "sampling": {
                "strategy": "stratified_by_field",
                "dataset": "source",
                "field": "label",
                "samples_per_value": 1,
            },
        }
    )
    stratified_datasets = {
        "source": DatasetDict(
            {
                "dev": Dataset.from_dict({"label": ["a", "b"]}),
                "test": Dataset.from_dict({"label": ["a", "a", "b"]}),
            }
        )
    }
    sampled = sample_evaluation_rows(stratified_datasets, stratified)
    assert {row["group_value"] for row in sampled} == {"a", "b"}
    assert {row["split"] for row in sampled} == {"dev", "test"}

    rows = [
        {"score": 8, "field": "history_fr", "split": "test", "status": "ok", "sample_group_value": "a", "sample_group_count": 2},
        {"score": 6, "field": "history_fr", "split": "test", "status": "ok", "sample_group_value": "b", "sample_group_count": 1},
        {"score": None, "field": "history_fr", "split": "test", "status": "error"},
    ]
    summary = evaluation_summary(rows)
    assert summary["overall"]["mean_score"] == 7.0
    assert summary["balanced_mean_score"] == 7.0
    assert summary["dataset_weighted_mean_score"] == 7.333


def test_judging_parsing_and_translation_judge() -> None:
    assert clamp_score(120) == 100.0
    assert parse_score_response('{"score": 80, "comment": "good"}') == (80.0, "good", "json")
    assert parse_score_response("```json\n{\"score\": 60, \"comment\": \"ok\"}\n```") == (60.0, "ok", "json")
    regex_score = parse_score_response("score: 72.5\nreason: ok")
    assert regex_score[0] == 72.5
    assert parse_score_response("nonsense")[2] == "parse_error"

    success = success_response(
        content='{"score": 92, "comment": "great"}',
        attempts=2,
        usage={"prompt_tokens": 10, "completion_tokens": 5},
        cost=0.1,
        finish_reason="stop",
        rate_limit_waits=1,
        rate_limit_wait_seconds=0.2,
    )
    judge = TranslationJudge(
        adapter=FakeJudgeAdapter(success),
        model="test-model",
        system_prompt="sys",
        prompt_template="{source_lang}:{target_lang}:{domain}:{source_text}:{translation}:{reference_text}",
        max_completion_tokens=20,
        temperature=0.0,
    )

    async def run_success():
        return await judge.score(
            source_text="hello",
            translation_text="bonjour",
            source_lang="English",
            target_lang="French",
            domain="general",
        )

    result = anyio.run(run_success)
    assert result["score"] == 92.0
    assert result["status"] == "ok"

    failure_judge = TranslationJudge(
        adapter=FakeJudgeAdapter(error_response(attempts=1, error="boom", rate_limit_waits=0, rate_limit_wait_seconds=0.0)),
        model="test-model",
        system_prompt="sys",
        prompt_template="{source_lang}:{target_lang}:{domain}:{source_text}:{translation}:{reference_text}",
        max_completion_tokens=20,
        temperature=0.0,
    )

    async def run_error():
        return await failure_judge.score(
            source_text="hello",
            translation_text="bonjour",
            source_lang="English",
            target_lang="French",
            domain="general",
            score_key="llm_score",
        )

    error_result = anyio.run(run_error)
    assert error_result["llm_score"] is None
    assert error_result["status"] == "error"


def test_llm_response_helpers_and_json_report(tmp_path: Path) -> None:
    class Choice:
        finish_reason = "stop"

    class Response:
        def __init__(self):
            self.choices = [Choice()]
            self.usage = {"prompt_tokens": 1, "completion_tokens": 2, "total_cost": 0.3}

    usage, cost = extract_usage(Response())
    assert usage["prompt_tokens"] == 1
    assert cost == 0.3
    assert extract_finish_reason(Response()) == "stop"

    report_path = tmp_path / "summary.json"
    write_json_report(report_path, {"ok": True})
    assert report_path.read_text(encoding="utf-8").strip().startswith("{")


def test_llm_response_helpers_cover_payload_dict_paths() -> None:
    class Response:
        def model_dump(self):
            return {
                "usage": {"prompt_tokens": 2, "estimated_cost": 0.4},
                "choices": [{"finish_reason": "length"}],
            }

    usage, cost = extract_usage(Response())
    assert usage["prompt_tokens"] == 2
    assert cost == 0.4
    assert extract_finish_reason(Response()) == "length"


def test_benchmark_sampling_and_reporting() -> None:
    benchmark = BenchmarkSpecModel.model_validate(
        {
            "dataset": "bench",
            "dataset_config": "default",
            "split": "train",
            "models": ["m1"],
            "language_pairs": ["en-ru"],
            "domains": ["general"],
            "years": [2024],
            "sample_size_per_language_pair": 1,
            "sample_size_total": 0,
            "sampling_score_thresholds": [50.0],
            "seed": 42,
            "source_column": "src",
            "translation_column": "mt",
            "reference_column": "",
            "human_score_column": "score",
            "language_pair_column": "dataset",
            "domain_column": "domain",
            "year_column": "year",
            "system_column": "system",
            "human_score_min": 0.0,
            "human_score_max": 100.0,
            "human_higher_is_better": True,
            "bin_labels": ["bad", "good"],
            "bin_thresholds": [50.0],
            "max_source_chars": 50,
            "max_translation_chars": 50,
        }
    )
    filters = build_benchmark_filters(benchmark)
    row = {"dataset": "set/en_ru", "domain": "general", "year": 2024, "src": "hello", "mt": "bonjour", "score": 70, "system": "sys"}
    assert row_allowed_for_benchmark(row, benchmark, filters=filters) is True
    assert row_allowed_for_benchmark({**row, "mt": ""}, benchmark, filters=filters) is False

    samples = sample_benchmark_rows([row, {**row, "score": 20, "dataset": "set/en_ru"}], benchmark)
    assert len(samples) == 1
    assert samples[0]["_lp"] == "en-ru"

    rows = [
        {
            "model": "m1",
            "status": "ok",
            "llm_score": 80.0,
            "human_score_raw": 80.0,
            "human_bin": "good",
            "llm_bin": "good",
            "lp": "en-ru",
        },
        {
            "model": "m1",
            "status": "ok",
            "llm_score": 20.0,
            "human_score_raw": 20.0,
            "human_bin": "bad",
            "llm_bin": "bad",
            "lp": "en-ru",
        },
        {
            "model": "m1",
            "status": "error",
            "llm_score": None,
            "human_score_raw": None,
            "human_bin": None,
            "llm_bin": None,
            "lp": "en-ru",
        },
    ]
    summary = benchmark_summary(rows, ["bad", "good"])
    assert summary["models"]["m1"]["ok_rows"] == 2
    assert summary["models"]["m1"]["mean_human_score"] == 50.0
    assert "by_language_pair" in summary["models"]["m1"]


def test_benchmark_sampling_total_mode_and_filter_rejections() -> None:
    benchmark = BenchmarkSpecModel.model_validate(
        {
            "dataset": "bench",
            "dataset_config": "default",
            "split": "train",
            "models": ["m1"],
            "language_pairs": [],
            "domains": [],
            "years": [],
            "sample_size_per_language_pair": 0,
            "sample_size_total": 2,
            "sampling_score_thresholds": [],
            "seed": 7,
            "source_column": "src",
            "translation_column": "mt",
            "reference_column": "",
            "human_score_column": "score",
            "language_pair_column": "dataset",
            "domain_column": "domain",
            "year_column": "year",
            "system_column": "system",
            "human_score_min": 0.0,
            "human_score_max": 100.0,
            "human_higher_is_better": True,
            "bin_labels": ["bad", "good"],
            "bin_thresholds": [50.0],
            "max_source_chars": 5,
            "max_translation_chars": 5,
        }
    )
    filters = build_benchmark_filters(benchmark)
    too_long = {"dataset": "set/en_ru", "domain": "general", "year": 2024, "src": "hello!", "mt": "ok", "score": 70}
    assert row_allowed_for_benchmark(too_long, benchmark, filters=filters) is False

    dataset = [
        {"dataset": "set/en_ru", "domain": "general", "year": 2024, "src": "hi", "mt": "yo", "score": 70},
        {"dataset": "set/en_de", "domain": "general", "year": 2024, "src": "ab", "mt": "cd", "score": 40},
        {"dataset": "set/en_fr", "domain": "general", "year": 2024, "src": "ef", "mt": "gh", "score": 60},
    ]
    samples = sample_benchmark_rows(dataset, benchmark)
    assert len(samples) == 2
    assert all("_dataset_idx" in row for row in samples)
