from pathlib import Path
from typing import Any

import yaml
from datasets import DatasetDict

from data_translate.config.loader import load_workflow_model
from data_translate.config.models_quality import QualityConfigModel, QualityRulesFromDatasetModel
from data_translate.config.models_workflow import ReformatWorkflowConfigModel, TranslateWorkflowConfigModel
from data_translate.domain.translation_quality import QualityRule
from data_translate.services.datasets import load_source_dataset
from data_translate.services.upload_datasets import select_upload_configs


def translation_rules(config: TranslateWorkflowConfigModel) -> list[QualityRule]:
    translation = config.dataset.translation
    if translation is None:
        return []
    return [
        QualityRule(
            source=rule.source,
            target=str(rule.target or rule.source),
            strategy=rule.strategy,
            options=dict(rule.options),
        )
        for rule in translation.rules
    ]


def reformat_rules(config: ReformatWorkflowConfigModel) -> list[QualityRule]:
    reformat = config.dataset.reformat
    if reformat is None:
        return []
    rules = reformat.rules
    return [
        QualityRule(
            source=rules.source_text_field,
            target=rules.target_text_field,
            strategy="text",
            options={},
        ),
        QualityRule(
            source=rules.source_history_field,
            target=rules.target_history_field,
            strategy="dialog_turns_content",
            options={"content_field": rules.history_content_field},
        ),
    ]


def _quality_config_path(config_root: str, quality_id: str) -> Path:
    return Path(config_root) / "quality" / f"{quality_id}.yaml"


def load_quality_config(config_root: str, quality_id: str) -> QualityConfigModel:
    path = _quality_config_path(config_root, quality_id)
    if not path.exists():
        raise FileNotFoundError(f"quality config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"quality config must be a mapping: {path}")
    payload.setdefault("quality_id", quality_id)
    return QualityConfigModel.model_validate(payload)


def _explicit_quality_rules(config: QualityConfigModel) -> list[QualityRule]:
    return [
        QualityRule(
            source=rule.source,
            target=str(rule.target or rule.source),
            strategy=rule.strategy,
            options=dict(rule.options),
        )
        for rule in config.rules
    ]


def _workflow_rules_from_dataset(
    *,
    spec: QualityRulesFromDatasetModel,
    config_root: str,
    overrides: list[str],
) -> list[QualityRule]:
    workflows = ["translate", "reformat"] if spec.workflow == "auto" else [spec.workflow]
    last_error: Exception | None = None
    for workflow in workflows:
        try:
            config = load_workflow_model(
                workflow,
                config_root=config_root,
                dataset_id=spec.dataset_id,
                run_name=spec.run or None,
                overrides=overrides,
            )
        except Exception as exc:
            last_error = exc
            continue
        if isinstance(config, TranslateWorkflowConfigModel):
            return translation_rules(config)
        if isinstance(config, ReformatWorkflowConfigModel):
            return reformat_rules(config)
        raise TypeError(f"unsupported workflow config for quality rules: {type(config).__name__}")
    if last_error is not None:
        raise last_error
    raise ValueError(f"could not load rules from dataset {spec.dataset_id}")


def _upload_transforms_for_rules(
    *,
    config_root: str,
    upload_id: str,
    upload_config_name: str,
) -> list[dict[str, Any]]:
    selection = select_upload_configs(config_root=config_root, upload_ids=[upload_id], all_uploads=False)[0]
    export = selection.config["export"]
    layout = str(export["layout"])
    if layout == "single_config":
        configured_name = str(export.get("config_name") or "default")
        if upload_config_name and upload_config_name != configured_name:
            raise ValueError(
                f"upload {upload_id} has single config {configured_name!r}, not {upload_config_name!r}"
            )
        return list(export.get("transforms", []))
    if layout == "multi_config":
        if not upload_config_name:
            raise ValueError(f"upload {upload_id} has multiple configs; set rules_from.upload_config")
        for config_entry in export["configs"]:
            if str(config_entry["config_name"]) == upload_config_name:
                return list(config_entry.get("transforms", []))
        raise ValueError(f"upload {upload_id} has no config named {upload_config_name!r}")
    raise ValueError(f"unknown upload layout: {layout}")


def _upload_target_field_map(transforms: list[dict[str, Any]]) -> dict[str, str]:
    field_map: dict[str, str] = {}
    for transform in transforms:
        name = str(transform.get("name", ""))
        if name == "replace_columns":
            for output_column, source_column in dict(transform.get("columns") or {}).items():
                field_map[str(source_column)] = str(output_column)
        elif name == "serialized_dialog_content":
            translated_column = str(transform.get("translated_column", ""))
            output_column = str(transform.get("column", ""))
            if translated_column and output_column:
                field_map[translated_column] = output_column
    return field_map


def apply_upload_target_mapping(rules: list[QualityRule], transforms: list[dict[str, Any]]) -> list[QualityRule]:
    field_map = _upload_target_field_map(transforms)
    if not field_map:
        return rules
    return [
        QualityRule(
            source=rule.source,
            target=field_map.get(rule.target, rule.target),
            strategy=rule.strategy,
            options=dict(rule.options or {}),
        )
        for rule in rules
    ]


def quality_rules(
    *,
    config: QualityConfigModel,
    config_root: str,
    overrides: list[str],
) -> list[QualityRule]:
    if config.rules:
        return _explicit_quality_rules(config)
    if config.rules_from is None:
        return []
    rules = _workflow_rules_from_dataset(spec=config.rules_from, config_root=config_root, overrides=overrides)
    if config.rules_from.upload_id:
        transforms = _upload_transforms_for_rules(
            config_root=config_root,
            upload_id=config.rules_from.upload_id,
            upload_config_name=config.rules_from.upload_config,
        )
        rules = apply_upload_target_mapping(rules, transforms)
    return rules


def _normalize_translated_splits(
    *,
    source: DatasetDict,
    translated: DatasetDict,
    split_map: dict[str, str],
) -> DatasetDict:
    if not split_map:
        return translated
    normalized = DatasetDict()
    for source_split in source:
        target_split = split_map.get(source_split, source_split)
        if target_split in translated:
            normalized[source_split] = translated[target_split]
    return normalized


def quality_config_inputs(
    *,
    quality_id: str,
    run_name: str,
    config_root: str,
    overrides: list[str],
) -> tuple[DatasetDict, DatasetDict, list[QualityRule], Path, dict[str, Any], list[str]]:
    config = load_quality_config(config_root, quality_id)
    source = load_source_dataset(config.source)
    translated = load_source_dataset(config.translation)
    translated = _normalize_translated_splits(source=source, translated=translated, split_map=config.split_map)
    rules = quality_rules(config=config, config_root=config_root, overrides=overrides)
    summary_path = Path("results") / config.quality_id / "check-translation" / (run_name or "default") / "summary.json"
    return source, translated, rules, summary_path, {
        "mode": "quality",
        "quality_id": config.quality_id,
        "run_name": run_name or "",
        "source": config.source.model_dump(mode="python"),
        "translation": config.translation.model_dump(mode="python"),
        "split_map": dict(config.split_map),
        "rules_from": config.rules_from.model_dump(mode="python") if config.rules_from else None,
        "rule_count": len(rules),
    }, list(config.allowed_extra_splits)
