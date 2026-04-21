from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datasets import Dataset, DatasetDict

from data_translate.config.loader import load_workflow_model
from data_translate.config.models_runtime_inputs import InputDatasetModel
from data_translate.services.datasets import DATASET_RESOLVER
from data_translate.domain.preflight import validate_evaluation_inputs, validate_translate_inputs
from data_translate.engine.manifests import build_manifest_payload, read_manifest, write_manifest


class ConfigInvariantTests(unittest.TestCase):
    def test_missing_run_preset_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_workflow_model("translate", dataset_id="faithdial", run_name="missing-run")

    def test_translate_materialized_output_path_includes_run_name(self) -> None:
        config = load_workflow_model("translate", dataset_id="faithdial", run_name="deepl")
        self.assertEqual(
            config.artifacts.materialized_output_path,
            "data/translated/fr/DeepPavlov_FaithDial/deepl",
        )

    def test_reformat_materialized_output_path_includes_run_name(self) -> None:
        config = load_workflow_model("reformat", dataset_id="globalwoz", run_name="ff")
        self.assertEqual(
            config.artifacts.materialized_output_path,
            "data/translated/fr/globalwoz_candidates/ff",
        )

    def test_path_input_model_allows_late_workflow_specific_override(self) -> None:
        model = InputDatasetModel(kind="path", path="")
        self.assertEqual(model.path, "")

    def test_evaluate_requires_non_empty_explicit_path_inputs(self) -> None:
        with self.assertRaises(ValueError):
            load_workflow_model("evaluate", dataset_id="globalwoz")

    def test_manifest_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            payload = build_manifest_payload(
                artifact_kind="translated_dataset",
                workflow="translate",
                dataset_id="faithdial",
                run_name="deepl",
                output_path=str(root),
                target_lang="fr",
            )
            write_manifest(root, payload)
            loaded = read_manifest(root)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["dataset_id"], "faithdial")

    def test_translated_input_uses_explicit_run_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            translated_root = Path(tmp) / "deepl"
            translated_root.mkdir(parents=True, exist_ok=True)
            config = load_workflow_model(
                "evaluate",
                dataset_id="faithdial",
                overrides=["+evaluation.inputs.translation.run_name=deepl"],
            )
            with patch("data_translate.services.datasets.build_materialized_output_path", return_value=translated_root):
                resolved = DATASET_RESOLVER.resolve_input_path(
                    config,
                    config.dataset.evaluation.inputs["translation"],
                )
            self.assertEqual(resolved, translated_root)


class PreflightInvariantTests(unittest.TestCase):
    def test_translate_preflight_requires_source_columns(self) -> None:
        config = load_workflow_model("translate", dataset_id="faithdial")
        translation = config.dataset.translation
        assert translation is not None
        dataset = DatasetDict({"test": Dataset.from_dict({"knowledge": ["k"]})})
        with self.assertRaises(ValueError):
            validate_translate_inputs(dataset, translation)

    def test_evaluate_preflight_detects_row_count_mismatch(self) -> None:
        config = load_workflow_model("evaluate", dataset_id="faithdial")
        datasets = {
            "source": DatasetDict(
                {
                    "test": Dataset.from_dict(
                        {
                            "history": [["hello"]],
                            "knowledge": ["fact"],
                        }
                    )
                }
            ),
            "translation": DatasetDict(
                {
                    "test": Dataset.from_dict(
                        {
                            "history_fr": [["bonjour"], ["salut"]],
                            "knowledge_fr": ["fait", "autre"],
                        }
                    )
                }
            ),
        }
        with self.assertRaises(ValueError):
            validate_evaluation_inputs(config, datasets, {"source": Path("."), "translation": Path(".")})

    def test_evaluate_preflight_detects_manifest_dataset_mismatch(self) -> None:
        config = load_workflow_model("evaluate", dataset_id="faithdial")
        datasets = {
            "source": DatasetDict(
                {
                    "test": Dataset.from_dict(
                        {
                            "history": [["hello"]],
                            "knowledge": ["fact"],
                        }
                    )
                }
            ),
            "translation": DatasetDict(
                {
                    "test": Dataset.from_dict(
                        {
                            "history_fr": [["bonjour"]],
                            "knowledge_fr": ["fait"],
                        }
                    )
                }
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            source_root = Path(tmp) / "source"
            translation_root = Path(tmp) / "translation"
            source_root.mkdir()
            translation_root.mkdir()
            write_manifest(
                translation_root,
                build_manifest_payload(
                    artifact_kind="translated_dataset",
                    workflow="translate",
                    dataset_id="wrong-dataset",
                    run_name="default",
                    output_path=str(translation_root),
                    target_lang="fr",
                ),
            )
            with self.assertRaises(ValueError):
                validate_evaluation_inputs(
                    config,
                    datasets,
                    {"source": source_root, "translation": translation_root},
                )


if __name__ == "__main__":
    unittest.main()
