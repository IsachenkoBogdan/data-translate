import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import anyio
import pytest
from datasets import Dataset, DatasetDict

from data_translate.adapters.llm_response import success_response
from data_translate.domain.benchmark_records import build_benchmark_error_record, build_benchmark_tasks, make_benchmark_record_processor
from data_translate.domain.evaluation_records import (
    build_evaluation_error_record,
    build_evaluation_tasks,
    make_evaluation_record_processor,
)
from data_translate.services.judges import build_llm_adapter, build_translation_judge
from data_translate.services.translation import run_translate_workflow
from data_translate.engine.judge_run import run_judge_records
from data_translate.engine.jsonl import load_jsonl, write_jsonl
from data_translate.engine.translation_run import TranslationRunResult
from data_translate.workflows import benchmark_judge, evaluate, inspect_source, reformat, translate
from data_translate.workflows.judge_entrypoint import JudgeRunSpec, run_judge_entrypoint
from data_translate.workflows.judge_specs import build_benchmark_judge_spec, build_evaluate_judge_spec
from data_translate.config.loader import load_workflow_model


class FakeJudge:
    def __init__(self, payload):
        self.payload = payload

    async def score(self, **kwargs):
        return dict(self.payload, seen=kwargs["source_text"])


def test_evaluation_and_benchmark_record_processors() -> None:
    eval_config = load_workflow_model("evaluate", dataset_id="faithdial")
    datasets = {
        "source": {"test": [{"history": ["h"], "knowledge": "k"}]},
        "translation": {"test": [{"history_fr": ["bonjour"], "knowledge_fr": "fait"}]},
    }
    tasks = build_evaluation_tasks(eval_config, [{"split": "test", "row_idx": 0, "group_value": "", "group_count": 1}])
    processor = make_evaluation_record_processor(
        config=eval_config,
        datasets=datasets,
        resolved_paths={"source": ".", "translation": "."},
        judge=FakeJudge({"score": 8, "status": "ok"}),
    )
    record = anyio.run(lambda: processor(tasks[0]))
    assert record["score"] == 8
    error_record = build_evaluation_error_record(eval_config, tasks[0], RuntimeError("boom"))
    assert error_record["status"] == "error"

    bench_config = load_workflow_model("benchmark-judge", run_name="translation_judge")
    task = build_benchmark_tasks(
        bench_config,
        [{"_dataset_idx": 0, "_lp": "en-ru", "src": "hello", "mt": "bonjour", "score": 70, "dataset": "set/en_ru"}],
    )[0]
    bench_processor = make_benchmark_record_processor(
        config=bench_config,
        judges={bench_config.benchmark.models[0]: FakeJudge({"llm_score": 7, "status": "ok"})},
        labels=["bad", "ok", "good"],
        thresholds=[6.0, 8.0],
    )
    record = anyio.run(lambda: bench_processor(task))
    assert record["llm_score"] == 7
    assert build_benchmark_error_record(bench_config, task, RuntimeError("boom"))["status"] == "error"


def test_judge_factory_and_run_records(tmp_path: Path) -> None:
    config = load_workflow_model("evaluate", dataset_id="faithdial")
    runtime = config.runtime
    llm = config.llm
    prompt = config.prompt

    with patch("data_translate.services.judges.build_llm_chat_adapter", return_value="adapter"):
        assert build_llm_adapter(runtime, llm) == "adapter"

    with patch("data_translate.services.judges.load_text", side_effect=["sys", "{source_text} -> {translation}"]):
        judge = build_translation_judge(
            adapter=AsyncMock(return_value=success_response(
                content='{"score": 8}',
                attempts=1,
                usage={},
                cost=None,
                finish_reason="stop",
                rate_limit_waits=0,
                rate_limit_wait_seconds=0.0,
            )),
            runtime=runtime,
            llm=llm,
            prompt=prompt,
        )
    assert judge.model == llm.model

    async def process_item(task: int) -> dict[str, object]:
        if task == 2:
            raise RuntimeError("boom")
        return {"sample_id": str(task), "status": "ok"}

    rows, summary = anyio.run(
        lambda: run_judge_records(
            records_path=tmp_path / "records.jsonl",
            summary_path=tmp_path / "summary.json",
            tasks=[1, 2],
            done_keys=set(),
            task_done_key=lambda task: str(task),
            record_done_key=lambda row: str(row["sample_id"]),
            process_item=process_item,
            on_process_error=lambda task, exc: {"sample_id": str(task), "status": "error", "error": str(exc)},
            concurrency=2,
            desc="judge",
            summary_builder=lambda rows: {"rows": len(rows)},
            summary_context={"workflow": "evaluate"},
        )
    )
    assert len(rows) == 2
    assert summary["workflow"] == "evaluate"


def test_run_judge_records_retries_only_non_ok_rows_and_rewrites_latest_record(tmp_path: Path) -> None:
    records_path = tmp_path / "records.jsonl"
    write_jsonl(
        records_path,
        [
            {"sample_id": "1", "status": "ok"},
            {"sample_id": "2", "status": "parse_error"},
        ],
    )
    processed: list[int] = []

    async def process_item(task: int) -> dict[str, object]:
        processed.append(task)
        return {"sample_id": str(task), "status": "ok"}

    rows, summary = anyio.run(
        lambda: run_judge_records(
            records_path=records_path,
            summary_path=tmp_path / "summary.json",
            tasks=[1, 2],
            done_keys={"1"},
            task_done_key=lambda task: str(task),
            record_done_key=lambda row: str(row["sample_id"]),
            process_item=process_item,
            on_process_error=None,
            concurrency=1,
            desc="judge",
            summary_builder=lambda current_rows: {"rows": len(current_rows)},
            summary_context={},
        )
    )

    assert processed == [2]
    assert rows == [{"sample_id": "1", "status": "ok"}, {"sample_id": "2", "status": "ok"}]
    assert load_jsonl(records_path) == rows
    assert summary["rows"] == 2


def test_workflow_wrappers_and_judge_entrypoint() -> None:
    eval_config = load_workflow_model("evaluate", dataset_id="faithdial")
    bench_config = load_workflow_model("benchmark-judge", run_name="translation_judge")
    reformat_config = load_workflow_model("reformat", dataset_id="globalwoz", run_name="ff")
    inspect_config = load_workflow_model("inspect-source", dataset_id="globalwoz", run_name="ff")
    translate_config = load_workflow_model("translate", dataset_id="faithdial")

    with patch("data_translate.workflows.evaluate.run_judge_entrypoint") as judge_entry:
        evaluate.run(eval_config)
        judge_entry.assert_called_once()
    with patch("data_translate.workflows.benchmark_judge.run_judge_entrypoint") as judge_entry:
        benchmark_judge.run(bench_config)
        judge_entry.assert_called_once()
    with patch("data_translate.workflows.reformat.run_candidate_entrypoint") as candidate_entry:
        reformat.run(reformat_config)
        candidate_entry.assert_called_once()
    with patch("data_translate.workflows.inspect_source.run_candidate_entrypoint") as candidate_entry:
        inspect_source.run(inspect_config)
        candidate_entry.assert_called_once()
    with patch("data_translate.workflows.translate.anyio.run") as anyio_run:
        translate.run(translate_config)
        anyio_run.assert_called_once()

    async def process_task(task: int) -> dict[str, object]:
        return {"sample_id": str(task)}

    spec = JudgeRunSpec(
        tasks=[1],
        done_keys=set(),
        task_done_key=lambda task: str(task),
        record_done_key=lambda row: str(row["sample_id"]),
        process_item=process_task,
        on_process_error=None,
        concurrency=1,
        desc="judge",
        summary_builder=lambda rows: {"rows": len(rows)},
        summary_context={},
        start_log={"x": 1},
    )
    with patch("data_translate.workflows.judge_entrypoint.build_llm_adapter", return_value=AsyncMock(close=AsyncMock())), patch(
        "data_translate.workflows.judge_entrypoint.run_judge_records", new=AsyncMock(return_value=([], {}))
    ) as run_records:
        result = anyio.run(lambda: run_judge_entrypoint.__globals__["_run"](eval_config, Mock(), lambda _config, _adapter: spec))
    assert result == {}
    run_records.assert_awaited_once()


def test_judge_specs_builders() -> None:
    eval_config = load_workflow_model("evaluate", dataset_id="faithdial")
    bench_config = load_workflow_model("benchmark-judge", run_name="translation_judge")

    with (
        patch("data_translate.workflows.judge_specs.DATASET_RESOLVER.resolve_evaluation_input_paths", return_value={"source": Path("."), "translation": Path(".")}),
        patch("data_translate.workflows.judge_specs.DATASET_RESOLVER.load_evaluation_inputs_from_paths", return_value={"source": {"test": [{"history": ["h"], "knowledge": "k"}]}, "translation": {"test": [{"history_fr": ["bonjour"], "knowledge_fr": "fait"}]}}),
        patch("data_translate.workflows.judge_specs.validate_evaluation_inputs"),
        patch("data_translate.workflows.judge_specs.sample_evaluation_rows", return_value=[{"split": "test", "row_idx": 0, "group_value": "", "group_count": 1}]),
        patch("data_translate.workflows.judge_specs.build_translation_judge", return_value=FakeJudge({"score": 8, "status": "ok"})),
    ):
        spec = build_evaluate_judge_spec(eval_config, AsyncMock())
    assert spec.desc == "evaluate"
    assert list(spec.tasks)

    fake_dataset = [{"_dataset_idx": 0, "_lp": "en-ru", "src": "hello", "mt": "bonjour", "score": 70, "dataset": "set/en_ru"}]
    with (
        patch("data_translate.workflows.judge_specs.load_dataset", return_value=fake_dataset),
        patch("data_translate.workflows.judge_specs.sample_benchmark_rows", return_value=fake_dataset),
        patch("data_translate.workflows.judge_specs.build_translation_judge", return_value=FakeJudge({"llm_score": 7, "status": "ok"})),
    ):
        spec = build_benchmark_judge_spec(bench_config, AsyncMock())
    assert spec.desc == "benchmark-judge"
    assert list(spec.tasks)


def test_run_translate_workflow_writes_artifacts_and_closes_adapter(tmp_path: Path) -> None:
    config = load_workflow_model("translate", dataset_id="faithdial")
    config.artifacts.materialized_output_path = str(tmp_path / "translated")
    config.artifacts.checkpoint_dir = str(tmp_path / "checkpoints")
    config.artifacts.records_path = str(tmp_path / "records.jsonl")
    config.artifacts.summary_path = str(tmp_path / "summary.json")

    source_dataset = DatasetDict({"train": Dataset.from_dict({"dummy": ["hello"]})})
    translated_dataset = DatasetDict({"train": Dataset.from_dict({"dummy_fr": ["bonjour"]})})
    adapter = Mock()

    with (
        patch("data_translate.services.translation.load_source_dataset", return_value=source_dataset),
        patch("data_translate.services.translation.validate_translate_inputs"),
        patch("data_translate.services.translation.build_translation_adapter", return_value=adapter),
        patch(
            "data_translate.services.translation.translate_dataset_splits",
            new=AsyncMock(return_value=TranslationRunResult(dataset=translated_dataset, failed_splits=[])),
        ),
    ):
        summary = anyio.run(run_translate_workflow, config, Mock())

    output_path = Path(config.artifacts.materialized_output_path)
    summary_path = Path(config.artifacts.summary_path)
    records_path = Path(config.artifacts.records_path)
    manifest_path = output_path / "data-translate-manifest.json"

    assert summary["output"] == str(output_path)
    assert summary["failed_splits"] == []
    assert output_path.exists()
    assert manifest_path.exists()
    assert records_path.exists()
    assert json.loads(summary_path.read_text(encoding="utf-8"))["output"] == str(output_path)
    adapter.close.assert_called_once_with()


def test_run_translate_workflow_stops_before_writing_dataset_when_errors_not_allowed(tmp_path: Path) -> None:
    config = load_workflow_model("translate", dataset_id="faithdial")
    config.runtime.allow_errors = False
    config.artifacts.materialized_output_path = str(tmp_path / "translated")
    config.artifacts.checkpoint_dir = str(tmp_path / "checkpoints")
    config.artifacts.records_path = str(tmp_path / "records.jsonl")
    config.artifacts.summary_path = str(tmp_path / "summary.json")

    source_dataset = DatasetDict({"train": Dataset.from_dict({"dummy": ["hello"]})})
    translated_dataset = DatasetDict({"train": Dataset.from_dict({"dummy_fr": ["bonjour"]})})
    adapter = Mock()

    with (
        patch("data_translate.services.translation.load_source_dataset", return_value=source_dataset),
        patch("data_translate.services.translation.validate_translate_inputs"),
        patch("data_translate.services.translation.build_translation_adapter", return_value=adapter),
        patch(
            "data_translate.services.translation.translate_dataset_splits",
            new=AsyncMock(return_value=TranslationRunResult(dataset=translated_dataset, failed_splits=["train"])),
        ),
    ):
        with pytest.raises(RuntimeError, match="translation errors found"):
            anyio.run(run_translate_workflow, config, Mock())

    assert not Path(config.artifacts.materialized_output_path).exists()
    assert not Path(config.artifacts.summary_path).exists()
    adapter.close.assert_called_once_with()


def test_run_translate_workflow_attaches_passthrough_splits(tmp_path: Path) -> None:
    config = load_workflow_model("translate", dataset_id="statcan-dialogue-dataset-retrieval")
    config.artifacts.materialized_output_path = str(tmp_path / "translated")
    config.artifacts.checkpoint_dir = str(tmp_path / "checkpoints")
    config.artifacts.records_path = str(tmp_path / "records.jsonl")
    config.artifacts.summary_path = str(tmp_path / "summary.json")

    source_dataset = DatasetDict({"train": Dataset.from_dict({"query": ['[{"role":"user","content":"hello"}]']})})
    translated_dataset = DatasetDict({"train": Dataset.from_dict({"query": ['[{"role":"user","content":"hello"}]'], "query_fr": ['[{"role":"user","content":"hello","content_fr":"bonjour"}]']})})
    passthrough_dataset = DatasetDict({"french": Dataset.from_dict({"doc_id": ["D1"], "title": ["Titre"], "doc": ["Texte"]})})
    adapter = Mock()

    with (
        patch("data_translate.services.translation.load_source_dataset", side_effect=[source_dataset, passthrough_dataset]),
        patch("data_translate.services.translation.validate_translate_inputs"),
        patch("data_translate.services.translation.build_translation_adapter", return_value=adapter),
        patch(
            "data_translate.services.translation.translate_dataset_splits",
            new=AsyncMock(return_value=TranslationRunResult(dataset=translated_dataset, failed_splits=[])),
        ),
    ):
        summary = anyio.run(run_translate_workflow, config, Mock())

    output_path = Path(config.artifacts.materialized_output_path)
    saved = DatasetDict.load_from_disk(str(output_path))
    assert summary["failed_splits"] == []
    assert set(saved.keys()) == {"train", "corpus"}
    assert saved["corpus"]["doc_id"] == ["D1"]
    adapter.close.assert_called_once_with()


def test_run_translate_workflow_requires_translation_spec() -> None:
    config = SimpleNamespace(dataset=SimpleNamespace(translation=None))

    with pytest.raises(ValueError, match="requires dataset.translation"):
        anyio.run(run_translate_workflow, config, Mock())
