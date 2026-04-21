from data_translate.config.builder_common import (
    ConfigDict,
    MergePayloads,
    artifact_model,
    merge_model_overrides,
    require_dataset_section,
    scope_id,
    workflow_payload,
)
from data_translate.config.models_dataset import DatasetSpecModel
from data_translate.config.models_runtime import WorkflowMetaModel
from data_translate.config.models_workflow import TranslateWorkflowConfigModel
from data_translate.domain.languages import language_code
from data_translate.engine.artifacts import build_artifact_store



def build_translate_config(
    *,
    meta: WorkflowMetaModel,
    payload: ConfigDict,
    dataset: DatasetSpecModel | None,
    merge_payloads: MergePayloads,
) -> TranslateWorkflowConfigModel:
    dataset, translation = require_dataset_section(dataset, "translate", "translation")
    runtime_payload = merge_model_overrides(payload["runtime"], translation.runtime_overrides, merge_payloads)
    cache_namespace = translation.cache_namespace or f"translate_{translation.backend.provider}"
    store = build_artifact_store(
        workflow=meta.workflow,
        scope_id=scope_id(dataset, meta),
        run_name=meta.run_name,
        translated_basename=dataset.artifacts.translated_basename,
        target_lang=language_code(translation.target_lang),
        cache_namespace=cache_namespace,
        materialized_run_name=meta.run_name,
    )
    return TranslateWorkflowConfigModel.model_validate(
        workflow_payload(
            meta=meta,
            dataset=dataset,
            runtime=runtime_payload,
            artifacts=artifact_model(store),
        )
    )
