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
from data_translate.config.models_workflow import BenchmarkWorkflowConfigModel, EvaluateWorkflowConfigModel
from data_translate.config.models_workflow_benchmark import BenchmarkSpecModel
from data_translate.domain.languages import language_code
from data_translate.engine.artifacts import build_artifact_store



def build_evaluate_config(
    *,
    meta: WorkflowMetaModel,
    payload: ConfigDict,
    dataset: DatasetSpecModel | None,
    merge_payloads: MergePayloads,
) -> EvaluateWorkflowConfigModel:
    dataset, evaluation = require_dataset_section(dataset, "evaluate", "evaluation")
    for alias, ref in evaluation.inputs.items():
        if ref.kind == "path" and not ref.path.strip():
            raise ValueError(f"evaluate input dataset path must be set for alias {alias!r}")
    runtime_payload = merge_model_overrides(payload["runtime"], evaluation.runtime_overrides, merge_payloads)
    llm_payload = merge_model_overrides(payload["llm"], evaluation.llm_overrides, merge_payloads)
    prompt_payload = merge_model_overrides(payload["prompt"], evaluation.prompt_overrides, merge_payloads)
    translated_refs = [ref for ref in evaluation.inputs.values() if ref.kind == "translated"]
    target_lang = language_code(evaluation.target_lang) if translated_refs else ""
    translated_basename = dataset.artifacts.translated_basename if translated_refs else ""
    store = build_artifact_store(
        workflow=meta.workflow,
        scope_id=scope_id(dataset, meta),
        run_name=meta.run_name,
        translated_basename=translated_basename,
        target_lang=target_lang,
        cache_namespace="llm",
        materialized_run_name=meta.run_name if translated_refs else "",
    )
    return EvaluateWorkflowConfigModel.model_validate(
        workflow_payload(
            meta=meta,
            dataset=dataset,
            runtime=runtime_payload,
            llm=llm_payload,
            prompt=prompt_payload,
            artifacts=artifact_model(store),
        )
    )



def build_benchmark_config(
    *,
    meta: WorkflowMetaModel,
    payload: ConfigDict,
    dataset: DatasetSpecModel | None,
    merge_payloads: MergePayloads,
) -> BenchmarkWorkflowConfigModel:
    del dataset, merge_payloads
    benchmark = BenchmarkSpecModel.model_validate(payload["benchmark"])
    store = build_artifact_store(
        workflow=meta.workflow,
        scope_id=meta.run_name,
        run_name=meta.run_name,
        cache_namespace="llm",
    )
    return BenchmarkWorkflowConfigModel.model_validate(
        workflow_payload(
            meta=meta,
            runtime=payload["runtime"],
            llm=payload["llm"],
            prompt=payload["prompt"],
            benchmark=benchmark.model_dump(mode="python"),
            artifacts=artifact_model(store),
        )
    )
