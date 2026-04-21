from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import anyio
import pytest
from datasets import Dataset, DatasetDict

from data_translate.config.loader import load_workflow_model
from data_translate.engine.translation_run import TranslationRunResult
from data_translate.services.translation import build_translate_summary, require_translation_spec, run_translate_workflow


def test_require_translation_spec_and_build_summary() -> None:
    config = load_workflow_model("translate", dataset_id="faithdial")
    translation = require_translation_spec(config)
    summary = build_translate_summary(
        config,
        translation,
        output_path=Path("out"),
        manifest_path=Path("out/data-translate-manifest.json"),
        failed_splits=["test"],
    )
    assert summary["workflow"] == "translate"
    assert summary["failed_splits"] == ["test"]
    assert summary["manifest_path"].endswith("data-translate-manifest.json")


def test_run_translate_workflow_happy_path(tmp_path: Path) -> None:
    config = load_workflow_model("translate", dataset_id="faithdial")
    config.artifacts.checkpoint_dir = str(tmp_path / "checkpoint")
    config.artifacts.records_path = str(tmp_path / "records.jsonl")
    config.artifacts.summary_path = str(tmp_path / "summary.json")
    config.artifacts.materialized_output_path = str(tmp_path / "translated")
    translated = DatasetDict({"test": Dataset.from_dict({"history": [["bonjour"]], "knowledge": ["fait"], "history_fr": [["bonjour"]], "knowledge_fr": ["fait"]})})
    logger = Mock()
    adapter = Mock(close=Mock())

    with (
        patch("data_translate.services.translation.load_source_dataset", return_value=DatasetDict({"test": Dataset.from_dict({"history": [["hello"]], "knowledge": ["fact"]})})),
        patch("data_translate.services.translation.validate_translate_inputs"),
        patch("data_translate.services.translation.build_translation_adapter", return_value=adapter),
        patch(
            "data_translate.services.translation.translate_dataset_splits",
            new=AsyncMock(return_value=TranslationRunResult(dataset=translated, failed_splits=[])),
        ),
        patch("data_translate.services.translation.write_manifest", return_value=Path(tmp_path / "translated" / "data-translate-manifest.json")) as write_manifest_mock,
        patch("data_translate.services.translation.write_jsonl") as write_jsonl_mock,
        patch("data_translate.services.translation.write_json_report") as write_json_report_mock,
        patch("data_translate.services.translation.build_translate_records", return_value=[{"row_idx": 0}]),
    ):
        summary = anyio.run(run_translate_workflow, config, logger)

    assert summary["failed_splits"] == []
    assert write_manifest_mock.called
    assert write_jsonl_mock.called
    assert write_json_report_mock.called
    adapter.close.assert_called_once()
    assert logger.info.call_count == 2


def test_run_translate_workflow_rejects_failed_splits_when_errors_forbidden(tmp_path: Path) -> None:
    config = load_workflow_model("translate", dataset_id="faithdial")
    config.artifacts.checkpoint_dir = str(tmp_path / "checkpoint")
    config.artifacts.records_path = str(tmp_path / "records.jsonl")
    config.artifacts.summary_path = str(tmp_path / "summary.json")
    config.artifacts.materialized_output_path = str(tmp_path / "translated")
    logger = Mock()
    adapter = Mock(close=Mock())
    translated = DatasetDict({"test": Dataset.from_dict({"history": [["bonjour"]], "knowledge": ["fait"], "history_fr": [["bonjour"]], "knowledge_fr": ["fait"]})})

    with (
        patch("data_translate.services.translation.load_source_dataset", return_value=DatasetDict({"test": Dataset.from_dict({"history": [["hello"]], "knowledge": ["fact"]})})),
        patch("data_translate.services.translation.validate_translate_inputs"),
        patch("data_translate.services.translation.build_translation_adapter", return_value=adapter),
        patch(
            "data_translate.services.translation.translate_dataset_splits",
            new=AsyncMock(return_value=TranslationRunResult(dataset=translated, failed_splits=["test"])),
        ),
    ):
        with pytest.raises(RuntimeError, match="translation errors found"):
            anyio.run(run_translate_workflow, config, logger)

    adapter.close.assert_called_once()
