from collections.abc import Callable
from typing import Any

from data_translate.config.models_dataset import DatasetSpecModel
from data_translate.config.models_runtime import ArtifactPathsModel, WorkflowMetaModel
from data_translate.config.models_workflow_common import WorkflowConfigBaseModel
from data_translate.engine.artifacts import ArtifactStore


ConfigDict = dict[str, Any]
MergePayloads = Callable[[ConfigDict, ConfigDict], ConfigDict]
WorkflowBuilder = Callable[..., WorkflowConfigBaseModel]


def scope_id(dataset: DatasetSpecModel | None, meta: WorkflowMetaModel) -> str:
    if dataset is not None:
        return dataset.artifacts.results_scope or dataset.dataset_id
    return meta.run_name


def artifact_model(store: ArtifactStore) -> ArtifactPathsModel:
    return ArtifactPathsModel.model_validate(
        {
            "results_root": str(store.results_root),
            "records_path": str(store.records_path),
            "summary_path": str(store.summary_path),
            "checkpoint_dir": str(store.checkpoint_dir),
            "cache_dir": str(store.cache_dir),
            "materialized_output_path": str(store.materialized_output_path or ""),
        }
    )


def require_dataset(dataset: DatasetSpecModel | None, workflow: str) -> DatasetSpecModel:
    if dataset is None:
        raise ValueError(f"{workflow} workflow requires --dataset")
    return dataset


def require_dataset_section(dataset: DatasetSpecModel | None, workflow: str, section: str) -> tuple[DatasetSpecModel, Any]:
    resolved = require_dataset(dataset, workflow)
    section_value = getattr(resolved, section)
    if section_value is None:
        raise ValueError(f"{workflow} workflow requires dataset.{section}")
    return resolved, section_value


def merge_model_overrides(base: ConfigDict, override_model: Any, merge_payloads: MergePayloads) -> ConfigDict:
    return merge_payloads(base, override_model.model_dump(exclude_none=True))


def workflow_payload(
    *,
    meta: WorkflowMetaModel,
    artifacts: ArtifactPathsModel,
    dataset: DatasetSpecModel | None = None,
    **extra: Any,
) -> ConfigDict:
    payload: ConfigDict = {
        "meta": meta.model_dump(mode="python"),
        "artifacts": artifacts.model_dump(mode="python"),
        **extra,
    }
    if dataset is not None:
        payload["dataset"] = dataset.model_dump(mode="python")
    return payload
