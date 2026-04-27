import json
from pathlib import Path
from unittest.mock import Mock, patch

from datasets import Dataset, DatasetDict, load_from_disk

from data_translate.config.loader import load_workflow_model
from data_translate.domain.reformat_common import (
    convert_dialogue_rows,
    group_indices_by_dialogue,
    normalize_dialogue_id,
    normalize_dialogues,
)
from data_translate.domain.reformat_conversion import _materialize_reformatted_split, reformat_candidate
from data_translate.domain.reformat_inspection import inspect_candidate
from data_translate.engine.candidate_run import run_candidate_workflow
from data_translate.engine.jsonl import load_jsonl
from data_translate.workflows.candidate_entrypoint import run_candidate_entrypoint
from data_translate.workflows.candidate_processors import build_inspect_source_processor, build_reformat_processor


def _source_dataset() -> DatasetDict:
    return DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "dialogue_id": ["d1", "d1", "d2"],
                    "text": ["old1", "old2", "old3"],
                    "history": [
                        [],
                        [{"role": "user", "content": "old1"}],
                        [],
                    ],
                }
            )
        }
    )


def _candidate_payload() -> dict[str, object]:
    return {
        "d1": {"log": [{"text": "u1"}, {"text": "a1"}, {"text": "u2"}, {"text": "a2"}]},
        "d2": {"log": [{"text": "u3"}, {"text": "a3"}]},
        "extra": {"log": [{"text": "x"}, {"text": "y"}]},
    }


def test_reformat_common_helpers() -> None:
    config = load_workflow_model("reformat", dataset_id="globalwoz", run_name="ff")
    rules = config.dataset.reformat.rules
    assert normalize_dialogue_id("F&F_fr-d1", ["F&F_fr-"]) == "d1"
    assert normalize_dialogues({"F&F_fr-d1": {}}, ["F&F_fr-"]) == {"d1": {}}
    grouped = group_indices_by_dialogue(_source_dataset()["train"], "dialogue_id")
    assert grouped == {"d1": [0, 1], "d2": [2]}

    texts, histories = convert_dialogue_rows(_candidate_payload()["d1"], 2, rules)
    assert texts == ["u1", "u2"]
    assert histories[1] == [{"content": "u1", "role": "user"}, {"content": "a1", "role": "assistant"}]


def test_reformat_candidate_and_inspection(tmp_path: Path) -> None:
    config = load_workflow_model("reformat", dataset_id="globalwoz", run_name="ff")
    rules = config.dataset.reformat.rules
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(_candidate_payload()), encoding="utf-8")

    converted, summary = reformat_candidate(
        candidate_name="FF",
        candidate_path=candidate_path,
        rules=rules,
        source=_source_dataset(),
        missing_policy="keep_source",
    )
    assert summary["splits"]["train"]["output_rows"] == 3
    assert converted["train"]["text"] == ["u1", "u2", "u3"]
    assert converted["train"]["source_text"] == ["old1", "old2", "old3"]

    report = inspect_candidate(
        candidate_name="FF",
        candidate_path=candidate_path,
        rules=rules,
        source=_source_dataset(),
    )
    assert report["intersection"] == 2
    assert report["external_not_source"] == 1


def test_reformat_candidate_handles_missing_and_bad_dialogues(tmp_path: Path) -> None:
    config = load_workflow_model("reformat", dataset_id="globalwoz", run_name="ff")
    rules = config.dataset.reformat.rules
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        json.dumps(
            {
                "d1": {"log": [{"text": "u1"}]},
            }
        ),
        encoding="utf-8",
    )

    converted, summary = reformat_candidate(
        candidate_name="FF",
        candidate_path=candidate_path,
        rules=rules,
        source=_source_dataset(),
        missing_policy="drop",
    )
    split_summary = summary["splits"]["train"]
    assert split_summary["output_rows"] == 0
    assert split_summary["missing_dialogues"] == 1
    assert split_summary["bad_dialogues"] == 1
    assert converted["train"].num_rows == 0


def test_materialize_reformatted_split_handles_chunk_boundaries() -> None:
    config = load_workflow_model("reformat", dataset_id="globalwoz", run_name="ff")
    rules = config.dataset.reformat.rules
    dataset = Dataset.from_dict(
        {
            "dialogue_id": ["d1", "d2", "d3"],
            "text": ["old1", "old2", "old3"],
            "history": [
                [],
                [{"role": "user", "content": "old2"}],
                [{"role": "assistant", "content": "old3"}],
            ],
            "meta": ["m1", "m2", "m3"],
        }
    )

    materialized = _materialize_reformatted_split(
        dataset,
        keep_indices=[0, 1, 2],
        candidate_name="FF",
        rules=rules,
        new_text_by_idx={0: "new1", 2: "new3"},
        new_history_by_idx={1: [{"role": "user", "content": "new2"}]},
        chunk_size=1,
    )

    assert materialized["text"] == ["new1", "old2", "new3"]
    assert materialized["history"] == [
        [],
        [{"role": "user", "content": "new2"}],
        [{"role": "assistant", "content": "old3"}],
    ]
    assert materialized["source_text"] == ["old1", "old2", "old3"]
    assert materialized["source_history"] == [
        [],
        [{"role": "user", "content": "old2"}],
        [{"role": "assistant", "content": "old3"}],
    ]
    assert materialized["reformat_variant"] == ["FF", "FF", "FF"]
    assert materialized["meta"] == ["m1", "m2", "m3"]


def test_run_candidate_workflow_and_processors(tmp_path: Path) -> None:
    config = load_workflow_model("reformat", dataset_id="globalwoz", run_name="ff")
    config.artifacts.materialized_output_path = str(tmp_path / "translated")
    source = _source_dataset()
    rules = config.dataset.reformat
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(json.dumps(_candidate_payload()), encoding="utf-8")

    report, records = run_candidate_workflow(
        workflow="reformat",
        dataset_id="globalwoz",
        run_name="ff",
        records_path=tmp_path / "records.jsonl",
        summary_path=tmp_path / "summary.json",
        artifacts={"x": 1},
        external_root=tmp_path,
        selected_candidates=["FF"],
        candidate_paths={"FF": "candidate.json"},
        summary_key="profiles",
        process_candidate=lambda name, path: ({"candidate": name, "path": str(path)}, [{"candidate": name}]),
    )
    assert [row["record_type"] for row in records] == ["detail", "candidate_status"]
    assert records[0]["candidate"] == "FF"
    assert records[0]["attempt"] == 1
    assert records[1]["status"] == "ok"
    assert records[1]["attempt"] == 1
    assert report["profiles"]["FF"]["candidate"] == "FF"
    assert load_jsonl(tmp_path / "records.jsonl") == records

    processor = build_reformat_processor(config, source, rules)
    summary, rows = processor("FF", candidate_path)
    assert summary["candidate"] == "FF"
    saved = load_from_disk(str(Path(summary["output"])))
    assert saved["train"]["text"] == ["u1", "u2", "u3"]
    assert rows[0]["candidate"] == "FF"

    inspect_processor = build_inspect_source_processor(config, source, rules)
    inspect_summary, inspect_rows = inspect_processor("FF", candidate_path)
    assert inspect_summary["candidate"] == "FF"
    assert inspect_rows == [inspect_summary]


def test_run_candidate_workflow_skips_success_and_retries_previous_errors(tmp_path: Path) -> None:
    records_path = tmp_path / "records.jsonl"
    summary_path = tmp_path / "summary.json"
    calls: list[str] = []
    outcomes = {
        "ok": [({"candidate": "ok"}, [{"candidate": "ok"}])],
        "bad": [RuntimeError("boom"), ({"candidate": "bad"}, [{"candidate": "bad"}])],
    }

    def process_candidate(candidate_name: str, candidate_path: Path):
        del candidate_path
        calls.append(candidate_name)
        outcome = outcomes[candidate_name].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    first_report, first_records = run_candidate_workflow(
        workflow="inspect-source",
        dataset_id="globalwoz",
        run_name="ff",
        records_path=records_path,
        summary_path=summary_path,
        artifacts={"x": 1},
        external_root=tmp_path,
        selected_candidates=["ok", "bad"],
        candidate_paths={"ok": "ok.json", "bad": "bad.json"},
        summary_key="candidates",
        process_candidate=process_candidate,
    )
    second_report, second_records = run_candidate_workflow(
        workflow="inspect-source",
        dataset_id="globalwoz",
        run_name="ff",
        records_path=records_path,
        summary_path=summary_path,
        artifacts={"x": 1},
        external_root=tmp_path,
        selected_candidates=["ok", "bad"],
        candidate_paths={"ok": "ok.json", "bad": "bad.json"},
        summary_key="candidates",
        process_candidate=process_candidate,
    )

    assert calls == ["ok", "bad", "bad"]
    assert first_report["candidates"] == {"ok": {"candidate": "ok"}}
    assert first_report["errors"]["bad"]["status"] == "error"
    assert second_report["candidates"] == {"ok": {"candidate": "ok"}, "bad": {"candidate": "bad"}}
    assert "errors" not in second_report
    status_rows = [row for row in second_records if row["record_type"] == "candidate_status"]
    assert {row["candidate"]: row["attempt"] for row in status_rows} == {"ok": 1, "bad": 2}
    assert len([row for row in second_records if row["candidate"] == "bad"]) == 2
    assert len(second_records) > len(first_records)


def test_run_candidate_entrypoint_wires_components() -> None:
    config = load_workflow_model("inspect-source", dataset_id="globalwoz", run_name="ff")
    logger = Mock()
    source = _source_dataset()
    processor = lambda candidate_name, candidate_path: ({"candidate": candidate_name, "path": str(candidate_path)}, [])

    with (
        patch("data_translate.workflows.candidate_entrypoint.load_source_dataset", return_value=source),
        patch("data_translate.workflows.candidate_entrypoint.validate_reformat_inputs") as validate_mock,
        patch("data_translate.workflows.candidate_entrypoint.run_candidate_workflow") as run_mock,
    ):
        run_candidate_entrypoint(
            config=config,
            logger=logger,
            summary_key="candidates",
            processor_factory=lambda _config, _source, _reformat: processor,
        )

    validate_mock.assert_called_once()
    run_mock.assert_called_once()
    assert logger.info.call_count == 2
