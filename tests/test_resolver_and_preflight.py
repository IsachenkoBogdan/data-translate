from pathlib import Path
from unittest.mock import patch

import pytest
from datasets import Dataset, DatasetDict

from data_translate.config.loader import load_workflow_model
from data_translate.config.models_runtime_inputs import InputDatasetModel
from data_translate.services.datasets import DATASET_RESOLVER, DatasetResolver
from data_translate.domain.preflight import validate_evaluation_inputs, validate_reformat_inputs
from data_translate.engine.manifests import build_manifest_payload, write_manifest


def test_dataset_resolver_passes_hf_config_and_trust_remote_code() -> None:
    resolver = DatasetResolver()
    source = load_workflow_model("translate", dataset_id="faithdial").dataset.source.model_copy(
        update={"hf_config": "default", "hf_revision": "main", "trust_remote_code": True, "disk_path": ""}
    )
    with patch("data_translate.services.datasets.load_dataset", return_value="hf") as load_dataset_mock:
        result = resolver.load_source(source)
    assert result == "hf"
    load_dataset_mock.assert_called_once_with(
        path="DeepPavlov/FaithDial-ru",
        name="default",
        trust_remote_code=True,
    )


def test_dataset_resolver_prefers_local_disk_when_requested(tmp_path: Path) -> None:
    resolver = DatasetResolver()
    disk_root = tmp_path / "dataset"
    disk_root.mkdir()
    source = load_workflow_model("translate", dataset_id="faithdial").dataset.source.model_copy(
        update={"disk_path": str(disk_root), "prefer_local": True, "source_kind": "auto"}
    )

    with (
        patch("data_translate.services.datasets.load_dataset") as load_dataset_mock,
        patch("data_translate.services.datasets.load_from_disk", return_value="disk") as load_from_disk_mock,
    ):
        result = resolver.load_source(source)

    assert result == "disk"
    load_from_disk_mock.assert_called_once_with(str(disk_root))
    load_dataset_mock.assert_not_called()


def test_dataset_resolver_requires_existing_disk_path_for_disk_mode(tmp_path: Path) -> None:
    resolver = DatasetResolver()
    source = load_workflow_model("translate", dataset_id="faithdial").dataset.source.model_copy(
        update={"disk_path": str(tmp_path / "missing"), "hf_dataset_id": "", "source_kind": "disk"}
    )

    with pytest.raises(FileNotFoundError, match="source disk_path not found"):
        resolver.load_source(source)


def test_resolve_input_path_handles_raw_and_explicit_translated_path(tmp_path: Path) -> None:
    config = load_workflow_model("evaluate", dataset_id="faithdial")
    raw_root = tmp_path / "raw"
    translated_root = tmp_path / "translated"
    raw_root.mkdir()
    translated_root.mkdir()
    config.dataset.artifacts.raw_path = str(raw_root)

    raw_path = DATASET_RESOLVER.resolve_input_path(config, InputDatasetModel(kind="raw"))
    translated_path = DATASET_RESOLVER.resolve_input_path(
        config,
        InputDatasetModel(kind="translated", path=str(translated_root)),
    )

    assert raw_path == raw_root
    assert translated_path == translated_root


def test_resolve_evaluation_input_paths_allows_source_kind_without_local_path() -> None:
    config = load_workflow_model("evaluate", dataset_id="faithdial")
    config.dataset.evaluation.inputs["translation"] = InputDatasetModel(kind="path", path=".")

    input_paths = DATASET_RESOLVER.resolve_evaluation_input_paths(config)

    assert input_paths["source"] is None


def test_resolve_input_path_builds_translated_run_path_from_run_name(tmp_path: Path) -> None:
    config = load_workflow_model("evaluate", dataset_id="faithdial")
    translated_root = tmp_path / "translated" / "deepl"
    translated_root.mkdir(parents=True)

    with patch("data_translate.services.datasets.build_materialized_output_path", return_value=translated_root):
        translated_path = DATASET_RESOLVER.resolve_input_path(config, InputDatasetModel(kind="translated", run_name="deepl"))

    assert translated_path == translated_root


def test_resolve_input_path_rejects_missing_raw_configuration() -> None:
    config = load_workflow_model("evaluate", dataset_id="faithdial")
    config.dataset.artifacts.raw_path = ""
    config.dataset.source.disk_path = ""

    with pytest.raises(ValueError, match="raw input path is not configured"):
        DATASET_RESOLVER.resolve_input_path(config, InputDatasetModel(kind="raw"))


def test_resolve_input_path_rejects_missing_explicit_path(tmp_path: Path) -> None:
    config = load_workflow_model("evaluate", dataset_id="faithdial")
    missing = tmp_path / "missing"
    with pytest.raises(FileNotFoundError):
        DATASET_RESOLVER.resolve_input_path(config, InputDatasetModel(kind="path", path=str(missing)))


def test_load_evaluation_inputs_reads_all_aliases(tmp_path: Path) -> None:
    config = load_workflow_model("evaluate", dataset_id="faithdial")
    translation_root = tmp_path / "translation"
    translation_root.mkdir()
    config.dataset.evaluation.inputs["translation"] = InputDatasetModel(kind="path", path=str(translation_root))

    with (
        patch.object(DATASET_RESOLVER, "load_source", return_value="src") as load_source_mock,
        patch("data_translate.services.datasets.load_from_disk", return_value="tr") as load_from_disk_mock,
    ):
        datasets = DATASET_RESOLVER.load_evaluation_inputs(config)

    assert datasets == {"source": "src", "translation": "tr"}
    load_source_mock.assert_called_once()
    load_from_disk_mock.assert_called_once_with(str(translation_root))


def test_validate_evaluation_inputs_detects_manifest_target_and_run_mismatch(tmp_path: Path) -> None:
    config = load_workflow_model("evaluate", dataset_id="faithdial")
    datasets = {
        "source": DatasetDict({"test": Dataset.from_dict({"history": [["hello"]], "knowledge": ["fact"]})}),
        "translation": DatasetDict({"test": Dataset.from_dict({"history_fr": [["bonjour"]], "knowledge_fr": ["fait"]})}),
    }
    source_root = tmp_path / "source"
    translation_root = tmp_path / "translation"
    source_root.mkdir()
    translation_root.mkdir()
    write_manifest(
        translation_root,
        build_manifest_payload(
            artifact_kind="translated_dataset",
            workflow="translate",
            dataset_id="faithdial",
            run_name="other-run",
            output_path=str(translation_root),
            target_lang="de",
        ),
    )
    config.dataset.evaluation.inputs["translation"] = InputDatasetModel(kind="translated", run_name="deepl")
    with pytest.raises(ValueError, match="target_lang mismatch"):
        validate_evaluation_inputs(config, datasets, {"source": source_root, "translation": translation_root})


def test_validate_reformat_inputs_detects_missing_external_root() -> None:
    config = load_workflow_model("reformat", dataset_id="globalwoz", run_name="ff")
    source = DatasetDict(
        {
            "train": Dataset.from_dict({"dialogue_id": ["d1"], "text": ["x"], "history": [[{"role": "user", "content": "y"}]]})
        }
    )
    config.dataset.artifacts.external_root = "does-not-exist"
    with pytest.raises(FileNotFoundError, match="external_root not found"):
        validate_reformat_inputs(config, source, config.dataset.reformat)


def test_validate_reformat_inputs_detects_missing_candidate_file(tmp_path: Path) -> None:
    config = load_workflow_model("reformat", dataset_id="globalwoz", run_name="ff")
    source = DatasetDict(
        {
            "train": Dataset.from_dict({"dialogue_id": ["d1"], "text": ["x"], "history": [[{"role": "user", "content": "y"}]]})
        }
    )
    config.dataset.artifacts.external_root = str(tmp_path)
    with pytest.raises(FileNotFoundError, match="candidate 'FF' not found"):
        validate_reformat_inputs(config, source, config.dataset.reformat)
