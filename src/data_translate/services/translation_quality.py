from pathlib import Path
from typing import Any

from datasets import DatasetDict, load_from_disk

from data_translate.config.loader import load_workflow_model
from data_translate.config.models_workflow import ReformatWorkflowConfigModel, TranslateWorkflowConfigModel
from data_translate.domain.translation_quality import QualityReport, QualityRule, audit_translation_quality
from data_translate.domain.translation_quality_reporting import build_quality_metrics, render_quality_html
from data_translate.engine.jsonl import write_jsonl
from data_translate.engine.reports import write_json_report
from data_translate.services.datasets import load_source_dataset


def _translation_rules(config: TranslateWorkflowConfigModel) -> list[QualityRule]:
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


def _reformat_rules(config: ReformatWorkflowConfigModel) -> list[QualityRule]:
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


def _dataset_quality_inputs(
    *,
    dataset_id: str,
    run_name: str,
    config_root: str,
    overrides: list[str],
) -> tuple[DatasetDict, DatasetDict, list[QualityRule], Path, dict[str, Any], list[str]]:
    try:
        config = load_workflow_model(
            "translate",
            config_root=config_root,
            dataset_id=dataset_id,
            run_name=run_name or None,
            overrides=overrides,
        )
    except Exception:
        config = load_workflow_model(
            "reformat",
            config_root=config_root,
            dataset_id=dataset_id,
            run_name=run_name or None,
            overrides=overrides,
        )
        if not isinstance(config, ReformatWorkflowConfigModel):
            raise TypeError(f"expected reformat config for {dataset_id}")
        source = load_source_dataset(config.dataset.source)
        candidates = list((config.dataset.reformat.candidates if config.dataset.reformat else {}).keys())
        if not candidates:
            raise ValueError(f"reformat dataset {dataset_id} has no candidates")
        candidate = candidates[0]
        translated_path = Path(config.artifacts.materialized_output_path) / candidate
        translated = load_from_disk(str(translated_path))
        summary_path = Path("results") / dataset_id / "check-translation" / (run_name or "default") / "summary.json"
        return source, translated, _reformat_rules(config), summary_path, {
            "mode": "dataset",
            "workflow": "reformat",
            "dataset_id": dataset_id,
            "run_name": run_name or "",
            "translated_path": str(translated_path),
        }, []

    if not isinstance(config, TranslateWorkflowConfigModel):
        raise TypeError(f"expected translate config for {dataset_id}")
    source = load_source_dataset(config.dataset.source)
    translated_path = Path(config.artifacts.materialized_output_path)
    translated = load_from_disk(str(translated_path))
    summary_path = Path("results") / dataset_id / "check-translation" / (run_name or "default") / "summary.json"
    translation = config.dataset.translation
    passthrough_splits = [split.output_split for split in (translation.passthrough_splits if translation else [])]
    return source, translated, _translation_rules(config), summary_path, {
        "mode": "dataset",
        "workflow": "translate",
        "dataset_id": dataset_id,
        "run_name": run_name or "",
        "translated_path": str(translated_path),
    }, passthrough_splits


def _path_quality_inputs(path: str) -> tuple[None, DatasetDict, list[QualityRule], Path | None, dict[str, Any], list[str]]:
    translated = load_from_disk(path)
    if not isinstance(translated, DatasetDict):
        translated = DatasetDict({"train": translated})
    return None, translated, [], None, {"mode": "path", "translated_path": path}, []


def _effective_summary_path(summary_path: Path | None, max_rows_per_split: int) -> Path | None:
    if summary_path is None or max_rows_per_split <= 0:
        return summary_path
    report_dir = summary_path.parent
    sampled_dir = report_dir.with_name(f"{report_dir.name}-sample-{max_rows_per_split}")
    return sampled_dir / summary_path.name


def run_translation_quality_check(
    *,
    dataset_id: str = "",
    path: str = "",
    run_name: str = "",
    config_root: str = "conf",
    overrides: list[str] | None = None,
    max_issues: int = 50,
    max_rows_per_split: int = 0,
    show_progress: bool = False,
) -> dict[str, Any]:
    if not dataset_id and not path:
        raise ValueError("check-translation requires --dataset or --path")
    if dataset_id and path:
        raise ValueError("check-translation accepts either --dataset or --path, not both")

    if dataset_id:
        source, translated, rules, summary_path, context, allowed_extra_splits = _dataset_quality_inputs(
            dataset_id=dataset_id,
            run_name=run_name,
            config_root=config_root,
            overrides=list(overrides or []),
        )
    else:
        source, translated, rules, summary_path, context, allowed_extra_splits = _path_quality_inputs(path)
    summary_path = _effective_summary_path(summary_path, max_rows_per_split)

    report = audit_translation_quality(
        source=source,
        translated=translated,
        rules=rules,
        max_rows_per_split=max_rows_per_split,
        allowed_extra_splits=allowed_extra_splits,
        show_progress=show_progress,
    )
    payload = {
        "workflow": "check-translation",
        **context,
        "max_rows_per_split": max_rows_per_split,
        "splits": {split: len(translated[split]) for split in translated},
        **report.to_dict(),
    }
    metrics = build_quality_metrics(payload)
    if summary_path is not None:
        report_dir = summary_path.parent
        issues_path = report_dir / "issues.jsonl"
        suppressed_path = report_dir / "suppressed.jsonl"
        metrics_path = report_dir / "metrics.json"
        html_report_path = report_dir / "report.html"
        full_suppressed = [dict(item) for item in payload.get("suppressed", [])]
        payload["issues_path"] = str(issues_path)
        payload["suppressed_path"] = str(suppressed_path)
        payload["metrics_path"] = str(metrics_path)
        payload["html_report_path"] = str(html_report_path)
        if len(full_suppressed) > 200:
            payload["suppressed"] = full_suppressed[:200]
            payload["suppressed_truncated"] = True
        else:
            payload["suppressed"] = full_suppressed
            payload["suppressed_truncated"] = False
        write_json_report(summary_path, payload)
        write_jsonl(issues_path, [dict(issue) for issue in payload["issues"]])
        write_jsonl(suppressed_path, full_suppressed)
        write_json_report(metrics_path, metrics)
        html_report_path.write_text(render_quality_html(payload, metrics), encoding="utf-8")
        payload["summary_path"] = str(summary_path)
    display_issues = payload["issues"] if max_issues < 0 else payload["issues"][:max_issues]
    payload["display_issues"] = display_issues
    payload["issue_display_limit"] = max_issues
    payload["issue_count_truncated"] = max_issues >= 0 and len(display_issues) < len(payload["issues"])
    return payload


def format_quality_summary(payload: dict[str, Any]) -> str:
    lines = [
        f"check-translation: {payload.get('dataset_id') or payload.get('translated_path')}",
        f"checked_rows: {payload['checked_rows']}",
        f"errors: {payload['error_count']}",
        f"warnings: {payload['warning_count']}",
    ]
    if payload.get("summary_path"):
        lines.append(f"summary: {payload['summary_path']}")
    issues = payload.get("display_issues", payload.get("issues", []))
    if issues:
        lines.append("issues:")
        for issue in issues:
            lines.append(
                f"- {issue['severity']} {issue['code']} {issue['split']}[{issue['row_idx']}] "
                f"{issue['field']}: {issue['message']}"
            )
        if payload.get("issue_count_truncated"):
            lines.append(f"... truncated; full issue list is in {payload.get('issues_path') or payload.get('summary_path')}")
    return "\n".join(lines)
