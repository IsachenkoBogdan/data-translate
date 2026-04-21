import pathlib
from typing import Any

from hydra import compose, initialize_config_dir
from omegaconf import OmegaConf

from data_translate.config.models_runtime import WorkflowMetaModel
from data_translate.workflow_registry import get_workflow_definition


ConfigDict = dict[str, Any]


def _dataset_config_path(root: pathlib.Path, dataset_id: str) -> pathlib.Path:
    return root / "datasets" / f"{dataset_id}.yaml"


def _run_config_path(root: pathlib.Path, workflow: str, run_name: str) -> pathlib.Path:
    return root / "runs" / workflow / f"{run_name}.yaml"


def merge_payloads(base: ConfigDict, override: ConfigDict) -> ConfigDict:
    merged = OmegaConf.merge(base, override)
    payload = OmegaConf.to_container(merged, resolve=True)
    if not isinstance(payload, dict):
        raise ValueError("merged payload must be a mapping")
    return dict(payload)


def compose_raw_config(
    *,
    config_root: str | pathlib.Path,
    workflow: str,
    dataset_id: str | None,
    run_name: str | None,
    overrides: list[str] | None,
) -> ConfigDict:
    root = pathlib.Path(config_root).resolve()
    if not get_workflow_definition(workflow).dataset_optional and not dataset_id:
        raise ValueError(f"workflow {workflow!r} requires --dataset")
    if dataset_id and not _dataset_config_path(root, dataset_id).exists():
        raise FileNotFoundError(f"dataset config not found: {_dataset_config_path(root, dataset_id)}")
    if run_name and run_name != "default" and not _run_config_path(root, workflow, run_name).exists():
        raise FileNotFoundError(f"run config not found: {_run_config_path(root, workflow, run_name)}")
    hydra_overrides: list[str] = []
    if dataset_id:
        hydra_overrides.append(f"datasets@_global_={dataset_id}")
    if run_name:
        hydra_overrides.append(f"runs/{workflow}@_global_={run_name}")
    hydra_overrides.extend(overrides or [])
    with initialize_config_dir(version_base="1.3", config_dir=str(root)):
        cfg = compose(config_name=f"workflows/{workflow}", overrides=hydra_overrides)
    payload = OmegaConf.to_container(cfg, resolve=True)
    if not isinstance(payload, dict):
        raise ValueError("workflow config must compose to a mapping")
    resolved = dict(payload)
    resolved["workflow"] = workflow
    resolved["config_root"] = str(root)
    resolved["config_name"] = f"workflows/{workflow}"
    resolved["overrides"] = list(overrides or [])
    if dataset_id:
        resolved.setdefault("dataset_id", dataset_id)
    if run_name:
        resolved["run_name"] = resolved.get("run_name", run_name)
    else:
        resolved.setdefault("run_name", "default")
    return resolved


def dataset_payload(payload: ConfigDict) -> ConfigDict:
    fields = {"dataset_id", "source", "artifacts", "translation", "evaluation", "reformat"}
    return {key: payload[key] for key in fields if key in payload}


def workflow_meta(payload: ConfigDict) -> WorkflowMetaModel:
    return WorkflowMetaModel.model_validate(
        {
            "workflow": payload["workflow"],
            "dataset_id": payload.get("dataset_id"),
            "run_name": payload.get("run_name", "default"),
            "config_name": payload["config_name"],
            "config_root": payload["config_root"],
            "overrides": payload.get("overrides", []),
        }
    )


def compose_workflow_context(
    *,
    config_root: str | pathlib.Path,
    workflow: str,
    dataset_model_cls: type[Any],
    dataset_id: str | None,
    run_name: str | None,
    overrides: list[str] | None,
) -> tuple[ConfigDict, WorkflowMetaModel, Any | None]:
    payload = compose_raw_config(
        config_root=config_root,
        workflow=workflow,
        dataset_id=dataset_id,
        run_name=run_name,
        overrides=overrides,
    )
    meta = workflow_meta(payload)
    dataset = dataset_model_cls.model_validate(dataset_payload(payload)) if meta.dataset_id else None
    return payload, meta, dataset
