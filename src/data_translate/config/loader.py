import pathlib

from data_translate.config.builders import build_workflow_config
from data_translate.config.composition import compose_workflow_context, merge_payloads
from data_translate.config.models_dataset import DatasetSpecModel
from data_translate.config.models_workflow_common import WorkflowConfigBaseModel


def load_workflow_model(
    workflow: str,
    *,
    config_root: str = "conf",
    dataset_id: str | None = None,
    run_name: str | None = None,
    overrides: list[str] | None = None,
) -> WorkflowConfigBaseModel:
    payload, meta, dataset = compose_workflow_context(
        config_root=config_root,
        workflow=workflow,
        dataset_model_cls=DatasetSpecModel,
        dataset_id=dataset_id,
        run_name=run_name,
        overrides=overrides,
    )
    return build_workflow_config(
        workflow,
        meta=meta,
        payload=payload,
        dataset=dataset,
        merge_payloads=merge_payloads,
    )


def load_text(path: str | pathlib.Path) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")
