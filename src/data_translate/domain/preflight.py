from pathlib import Path

from datasets import DatasetDict

from data_translate.config.models_dataset_reformat import ReformatSpecModel
from data_translate.config.models_runtime_inputs import InputDatasetModel
from data_translate.config.models_dataset_translation import TranslationSpecModel
from data_translate.config.models_workflow import EvaluateWorkflowConfigModel, InspectSourceWorkflowConfigModel, ReformatWorkflowConfigModel, TranslateWorkflowConfigModel
from data_translate.domain.languages import language_code
from data_translate.engine.manifests import read_manifest


CandidateWorkflowConfig = ReformatWorkflowConfigModel | InspectSourceWorkflowConfigModel


def _required_splits(dataset: DatasetDict, requested_split: str) -> list[str]:
    if requested_split == "all":
        return list(dataset.keys())
    if requested_split not in dataset:
        raise ValueError(f"split {requested_split!r} is not present; available splits: {sorted(dataset.keys())}")
    return [requested_split]


def _require_columns(dataset: DatasetDict, split: str, columns: set[str], *, dataset_label: str) -> None:
    available = set(dataset[split].column_names)
    missing = sorted(columns - available)
    if missing:
        raise ValueError(
            f"{dataset_label} split {split!r} is missing required columns {missing}; "
            f"available columns: {sorted(available)}"
        )


def validate_translate_inputs(dataset: DatasetDict, translation: TranslationSpecModel) -> None:
    required_sources = {str(rule.source) for rule in translation.rules}
    for split in dataset:
        _require_columns(dataset, split, required_sources, dataset_label="source dataset")


def _validate_input_manifest(
    *,
    config: EvaluateWorkflowConfigModel,
    alias: str,
    ref: InputDatasetModel,
    path: Path | None,
) -> None:
    if path is None:
        return
    manifest = read_manifest(path)
    if manifest is None:
        return

    dataset_id = str(manifest.get("dataset_id", "")).strip()
    if dataset_id and dataset_id != (config.meta.dataset_id or ""):
        raise ValueError(
            f"manifest dataset_id mismatch for alias {alias!r}: expected {config.meta.dataset_id!r}, got {dataset_id!r}"
        )

    manifest_target_lang = str(manifest.get("target_lang", "")).strip()
    evaluation = config.dataset.evaluation
    if evaluation is not None and manifest_target_lang:
        if language_code(manifest_target_lang) != language_code(evaluation.target_lang):
            raise ValueError(
                f"manifest target_lang mismatch for alias {alias!r}: "
                f"expected {evaluation.target_lang!r}, got {manifest_target_lang!r}"
            )

    if ref.run_name and str(manifest.get("run_name", "")).strip() != ref.run_name:
        raise ValueError(
            f"manifest run_name mismatch for alias {alias!r}: expected {ref.run_name!r}, "
            f"got {manifest.get('run_name', '')!r}"
        )


def validate_evaluation_inputs(
    config: EvaluateWorkflowConfigModel,
    datasets: dict[str, DatasetDict],
    input_paths: dict[str, Path | None],
) -> None:
    evaluation = config.dataset.evaluation
    if evaluation is None:
        raise ValueError("evaluate workflow requires dataset.evaluation")

    split_names = _required_splits(datasets[evaluation.sampling.dataset], evaluation.split)
    sampling_columns = {str(evaluation.sampling.field)} if evaluation.sampling.strategy == "stratified_by_field" else set()
    required_columns_by_alias: dict[str, set[str]] = {alias: set() for alias in datasets}
    required_columns_by_alias[evaluation.sampling.dataset].update(sampling_columns)
    for field_pair in evaluation.field_pairs:
        required_columns_by_alias[field_pair.source_dataset].add(field_pair.source_field)
        required_columns_by_alias[field_pair.translation_dataset].add(field_pair.translation_field)
    row_counts: dict[tuple[str, str], int] = {}

    for alias, dataset in datasets.items():
        _validate_input_manifest(config=config, alias=alias, ref=evaluation.inputs[alias], path=input_paths[alias])
        for split in split_names:
            if split not in dataset:
                raise ValueError(f"dataset alias {alias!r} does not contain split {split!r}")
            required_columns = required_columns_by_alias.get(alias, set())
            if required_columns:
                _require_columns(dataset, split, required_columns, dataset_label=f"dataset alias {alias!r}")
            row_counts[(alias, split)] = len(dataset[split])

    checked_row_counts: set[tuple[str, str, str]] = set()
    for field_pair in evaluation.field_pairs:
        for split in split_names:
            pair_key = (field_pair.source_dataset, field_pair.translation_dataset, split)
            if pair_key in checked_row_counts:
                continue
            checked_row_counts.add(pair_key)
            source_size = row_counts[(field_pair.source_dataset, split)]
            translation_size = row_counts[(field_pair.translation_dataset, split)]
            if source_size != translation_size:
                raise ValueError(
                    f"row count mismatch for split {split!r}: "
                    f"{field_pair.source_dataset!r} has {source_size}, "
                    f"{field_pair.translation_dataset!r} has {translation_size}"
                )


def validate_reformat_inputs(config: CandidateWorkflowConfig, source: DatasetDict, reformat: ReformatSpecModel) -> None:
    required_source_columns = {
        reformat.rules.source_dialogue_id_field,
        reformat.rules.source_text_field,
        reformat.rules.source_history_field,
    }
    for split in source:
        _require_columns(source, split, required_source_columns, dataset_label="source dataset")

    external_root = Path(config.dataset.artifacts.external_root)
    if not external_root.exists():
        raise FileNotFoundError(f"external_root not found: {external_root}")
    for candidate_name, relative_path in reformat.candidates.items():
        candidate_path = external_root / relative_path
        if not candidate_path.exists():
            raise FileNotFoundError(f"candidate {candidate_name!r} not found: {candidate_path}")
