from data_translate.config.builder_common import ConfigDict, MergePayloads
from data_translate.config.models_dataset import DatasetSpecModel
from data_translate.config.models_runtime import WorkflowMetaModel
from data_translate.config.models_workflow_common import WorkflowConfigBaseModel
from data_translate.workflow_registry import get_workflow_definition


def build_workflow_config(
    workflow: str,
    *,
    meta: WorkflowMetaModel,
    payload: ConfigDict,
    dataset: DatasetSpecModel | None,
    merge_payloads: MergePayloads,
) -> WorkflowConfigBaseModel:
    definition = get_workflow_definition(workflow)
    config = definition.builder(meta=meta, payload=payload, dataset=dataset, merge_payloads=merge_payloads)
    if not isinstance(config, definition.config_model):
        raise TypeError(
            f"workflow {workflow!r} builder returned {type(config).__name__}, "
            f"expected {definition.config_model.__name__}"
        )
    return config
