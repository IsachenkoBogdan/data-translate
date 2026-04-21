from pathlib import Path
from typing import Any

import structlog
from datasets import DatasetDict

from data_translate.adapters.translation_factory import build_translation_adapter
from data_translate.config.models_dataset_translation import PassthroughSplitModel, TranslationSpecModel
from data_translate.config.models_workflow import TranslateWorkflowConfigModel
from data_translate.domain.preflight import validate_translate_inputs
from data_translate.domain.translation_checkpoints import build_translate_records
from data_translate.engine.jsonl import write_jsonl
from data_translate.engine.manifests import build_manifest_payload, write_manifest
from data_translate.engine.reports import write_json_report
from data_translate.engine.translation_run import translate_dataset_splits
from data_translate.services.datasets import dataset_fingerprints, load_source_dataset


def require_translation_spec(config: TranslateWorkflowConfigModel) -> TranslationSpecModel:
    translation = config.dataset.translation
    if translation is None:
        raise ValueError("translate workflow requires dataset.translation")
    return translation


def build_translate_summary(
    config: TranslateWorkflowConfigModel,
    translation: TranslationSpecModel,
    *,
    output_path: Path,
    manifest_path: Path,
    failed_splits: list[str],
) -> dict[str, Any]:
    return {
        "workflow": config.meta.workflow,
        "dataset_id": config.meta.dataset_id,
        "run_name": config.meta.run_name,
        "input": config.dataset.source.disk_path or config.dataset.source.hf_dataset_id,
        "output": str(output_path),
        "backend": translation.backend.model_dump(mode="python"),
        "artifacts": config.artifacts.model_dump(mode="python"),
        "runtime": config.runtime.model_dump(mode="python"),
        "manifest_path": str(manifest_path),
        "failed_splits": failed_splits,
    }


def _attach_passthrough_splits(
    translated: DatasetDict,
    *,
    passthrough_splits: list[PassthroughSplitModel],
) -> tuple[DatasetDict, dict[str, dict[str, object]]]:
    if not passthrough_splits:
        return translated, {}

    attached: dict[str, dict[str, object]] = {}
    merged = DatasetDict({split: split_dataset for split, split_dataset in translated.items()})
    for passthrough in passthrough_splits:
        extra_dataset = load_source_dataset(passthrough.source)
        if passthrough.source_split not in extra_dataset:
            raise ValueError(
                f"passthrough split {passthrough.source_split!r} not found in source {passthrough.source.hf_dataset_id or passthrough.source.disk_path}"
            )
        merged[passthrough.output_split] = extra_dataset[passthrough.source_split]
        attached[passthrough.output_split] = {
            "source": passthrough.source.model_dump(mode="python"),
            "source_split": passthrough.source_split,
        }
    return merged, attached


async def run_translate_workflow(
    config: TranslateWorkflowConfigModel,
    logger: structlog.stdlib.BoundLogger,
) -> dict[str, Any]:
    translation = require_translation_spec(config)
    dataset = load_source_dataset(config.dataset.source)
    validate_translate_inputs(dataset, translation)
    source_fingerprints = dataset_fingerprints(dataset)
    artifacts = config.artifacts
    adapter = build_translation_adapter(
        source_lang=translation.source_lang,
        target_lang=translation.target_lang,
        runtime=config.runtime,
        backend=translation.backend,
        cache_dir=artifacts.cache_dir,
    )
    output_path = Path(artifacts.materialized_output_path)

    logger.info(
        "translate.start",
        dataset_id=config.meta.dataset_id,
        run_name=config.meta.run_name,
        output=str(output_path),
        backend=translation.backend.provider,
        target_lang=translation.target_lang,
    )
    try:
        run_result = await translate_dataset_splits(
            dataset=dataset,
            translation=translation,
            runtime=config.runtime,
            checkpoint_dir=Path(artifacts.checkpoint_dir),
            adapter=adapter,
        )
        translated = run_result.dataset
        failed = run_result.failed_splits

        if failed and not config.runtime.allow_errors:
            raise RuntimeError(
                "translation errors found; checkpoints are saved, but final dataset was not written. "
                f"Failed rows by split: {failed}."
            )

        translated, attached_splits = _attach_passthrough_splits(
            translated,
            passthrough_splits=translation.passthrough_splits,
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        translated.save_to_disk(str(output_path))
        manifest = build_manifest_payload(
            artifact_kind="translated_dataset",
            workflow=config.meta.workflow,
            dataset_id=config.meta.dataset_id or "",
            run_name=config.meta.run_name,
            output_path=str(output_path),
            target_lang=translation.target_lang,
            extra={
                "source": config.dataset.source.model_dump(mode="python"),
                "source_fingerprints": source_fingerprints,
                "translation": translation.model_dump(mode="python"),
                "runtime": config.runtime.model_dump(mode="python"),
                "splits": {split: len(translated[split]) for split in translated},
                "passthrough_splits": attached_splits,
            },
        )
        manifest_path = write_manifest(output_path, manifest)
        write_jsonl(
            Path(artifacts.records_path),
            build_translate_records(Path(artifacts.checkpoint_dir), list(dataset.keys())),
        )
        summary = build_translate_summary(
            config,
            translation,
            output_path=output_path,
            manifest_path=manifest_path,
            failed_splits=failed,
        )
        write_json_report(Path(config.artifacts.summary_path), summary)
        logger.info("translate.done", dataset_id=config.meta.dataset_id, failed_splits=failed, output=str(output_path))
        return summary
    finally:
        adapter.close()
