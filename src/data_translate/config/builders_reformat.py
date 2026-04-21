from data_translate.config.builder_common import (
    ConfigDict,
    MergePayloads,
    artifact_model,
    require_dataset_section,
    scope_id,
    workflow_payload,
)
from data_translate.config.models_dataset import DatasetSpecModel
from data_translate.config.models_runtime import WorkflowMetaModel
from data_translate.config.models_workflow import InspectSourceWorkflowConfigModel, ReformatWorkflowConfigModel
from data_translate.domain.languages import language_code
from data_translate.engine.artifacts import build_artifact_store



def build_reformat_like_config(
    *,
    meta: WorkflowMetaModel,
    payload: ConfigDict,
    dataset: DatasetSpecModel | None,
    model_cls: type[ReformatWorkflowConfigModel] | type[InspectSourceWorkflowConfigModel],
) -> ReformatWorkflowConfigModel | InspectSourceWorkflowConfigModel:
    dataset, reformat = require_dataset_section(dataset, meta.workflow, "reformat")
    store = build_artifact_store(
        workflow=meta.workflow,
        scope_id=scope_id(dataset, meta),
        run_name=meta.run_name,
        translated_basename=dataset.artifacts.translated_basename,
        target_lang=language_code(reformat.target_lang),
        cache_namespace="reformat",
        materialized_run_name=meta.run_name,
    )
    return model_cls.model_validate(
        workflow_payload(
            meta=meta,
            dataset=dataset,
            artifacts=artifact_model(store),
        )
    )



def build_reformat_config(
    *,
    meta: WorkflowMetaModel,
    payload: ConfigDict,
    dataset: DatasetSpecModel | None,
    merge_payloads: MergePayloads,
) -> ReformatWorkflowConfigModel:
    del merge_payloads
    return build_reformat_like_config(
        meta=meta,
        payload=payload,
        dataset=dataset,
        model_cls=ReformatWorkflowConfigModel,
    )



def build_inspect_source_config(
    *,
    meta: WorkflowMetaModel,
    payload: ConfigDict,
    dataset: DatasetSpecModel | None,
    merge_payloads: MergePayloads,
) -> InspectSourceWorkflowConfigModel:
    del merge_payloads
    return build_reformat_like_config(
        meta=meta,
        payload=payload,
        dataset=dataset,
        model_cls=InspectSourceWorkflowConfigModel,
    )
