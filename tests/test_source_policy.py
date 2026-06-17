from pathlib import Path
from unittest.mock import patch

import pytest

from data_translate.config.models_dataset_source import SourceSpecModel
from data_translate.services.datasets import DatasetResolver


def test_source_defaults_to_hf_when_available() -> None:
    resolver = DatasetResolver()
    source = SourceSpecModel(
        disk_path="data/raw/local-copy",
        hf_dataset_id="DeepPavlov/FaithDial-ru",
    )
    with (
        patch.object(resolver, "resolve_source_path", return_value=Path("data/raw/local-copy")),
        patch("data_translate.services.datasets.load_dataset", return_value="hf-dataset") as load_dataset_mock,
        patch("data_translate.services.datasets.load_from_disk", return_value="disk-dataset") as load_from_disk_mock,
    ):
        result = resolver.load_source(source)

    assert result == "hf-dataset"
    load_dataset_mock.assert_called_once()
    load_from_disk_mock.assert_not_called()


def test_source_can_prefer_local_when_requested() -> None:
    resolver = DatasetResolver()
    source = SourceSpecModel(
        disk_path="data/raw/local-copy",
        hf_dataset_id="DeepPavlov/FaithDial-ru",
        prefer_local=True,
    )
    with (
        patch.object(resolver, "resolve_source_path", return_value=Path("data/raw/local-copy")),
        patch("data_translate.services.datasets.load_dataset", return_value="hf-dataset") as load_dataset_mock,
        patch("data_translate.services.datasets.load_from_disk", return_value="disk-dataset") as load_from_disk_mock,
    ):
        result = resolver.load_source(source)

    assert result == "disk-dataset"
    load_from_disk_mock.assert_called_once_with("data/raw/local-copy")
    load_dataset_mock.assert_not_called()


def test_source_kind_disk_requires_existing_path() -> None:
    resolver = DatasetResolver()
    source = SourceSpecModel(disk_path="data/raw/missing", source_kind="disk")
    with patch.object(resolver, "resolve_source_path", return_value=None):
        with pytest.raises(FileNotFoundError):
            resolver.load_source(source)


def test_source_model_rejects_prefer_local_for_hf_only() -> None:
    with pytest.raises(ValueError):
        SourceSpecModel(hf_dataset_id="DeepPavlov/FaithDial-ru", source_kind="hf", prefer_local=True)


def test_source_falls_back_to_dataset_viewer_for_script_datasets() -> None:
    resolver = DatasetResolver()
    source = SourceSpecModel(
        hf_dataset_id="McGill-NLP/TopiOCQA",
        hf_config="plain_text",
        hf_revision="main",
        source_kind="hf",
    )

    def fake_viewer_json(endpoint: str, params: dict[str, str | int]) -> dict:
        assert params["dataset"] == "McGill-NLP/TopiOCQA"
        assert params["revision"] == "main"
        if endpoint == "splits":
            return {"splits": [{"config": "plain_text", "split": "train"}]}
        if endpoint == "parquet":
            return {"parquet_files": []}
        if endpoint == "rows":
            assert params["config"] == "plain_text"
            assert params["split"] == "train"
            assert params["offset"] == 0
            assert params["length"] == 1
            return {
                "rows": [
                    {"row_idx": 0, "row": {"text": "hello"}},
                ],
                "num_rows_total": 2,
            }
        raise AssertionError(endpoint)

    with (
        patch(
            "data_translate.services.datasets.load_dataset",
            side_effect=RuntimeError("Dataset scripts are no longer supported, but found TopiOCQA.py"),
        ) as load_dataset_mock,
        patch.object(resolver, "_viewer_json", side_effect=fake_viewer_json),
    ):
        result = resolver.load_source(source, max_rows_per_split=1)

    assert list(result.keys()) == ["train"]
    assert result["train"]["text"] == ["hello"]
    load_dataset_mock.assert_called_once()
    assert load_dataset_mock.call_args.kwargs["revision"] == "main"
