import json
import re
from pathlib import Path
from typing import Any

import anyio

from data_translate.adapters.llm_base import LLMChatAdapter
from data_translate.config.loader import load_workflow_model
from data_translate.config.models_workflow import EvaluateWorkflowConfigModel
from data_translate.domain.translation_quality_reporting import render_fix_suggestions_html
from data_translate.engine.jsonl import write_jsonl
from data_translate.engine.progress import progress_bar
from data_translate.engine.reports import write_json_report
from data_translate.services.judges import build_llm_adapter
from data_translate.services.translation_quality import run_translation_quality_check


FIXABLE_CODES = {
    "unchanged_translation",
    "english_residue",
    "length_ratio_high",
    "length_ratio_low",
    "html_entity_leak",
}

FIX_SYSTEM_PROMPT = (
    "You are a professional translation repair assistant. Return ONLY valid JSON. "
    "Do not include markdown, explanations outside JSON, or alternative formats."
)

FIX_USER_PROMPT = """Fix the translation issue below.

Source language: {source_lang}
Target language: {target_lang}
Domain: {domain}
Issue code: {code}
Issue message: {message}

Source text:
{source_text}

Current translation:
{translation}

Return strict JSON:
{{
  "suggested_translation": "<one corrected translation in the target language>",
  "confidence": <number from 0 to 1>,
  "rationale": "<one short sentence>"
}}
"""


def _sample_text(issue: dict[str, Any], key: str) -> str:
    value = issue.get("sample", {}).get(key, "")
    if isinstance(value, str):
        return value.strip()
    return json.dumps(value, ensure_ascii=False)


def _group_text(value: str) -> str:
    return " ".join(value.split())


def _issue_location(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "split": issue.get("split"),
        "row_idx": issue.get("row_idx"),
        "field": issue.get("field"),
    }


def _fix_case_key(issue: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(issue.get("code", "")),
        str(issue.get("message", "")),
        _group_text(_sample_text(issue, "source")),
        _group_text(_sample_text(issue, "translation")),
    )


def _strip_code_fences(content: str) -> str:
    match = re.match(r"^```[a-zA-Z0-9_-]*\s*(.*?)\s*```$", content.strip(), re.DOTALL)
    return match.group(1).strip() if match else content.strip()


def _first_json_object(content: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    text = _strip_code_fences(content)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed
    for match in re.finditer(r"\{", text):
        try:
            candidate, _end = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(candidate, dict):
            return candidate
    return None


def _fixable_issues(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(issue)
        for issue in payload.get("issues", [])
        if str(issue.get("code", "")) in FIXABLE_CODES
        and str(issue.get("sample", {}).get("source", "")).strip()
        and str(issue.get("sample", {}).get("translation", "")).strip()
    ]


def _group_fix_cases(issues: list[dict[str, Any]], max_fixes: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for issue in issues:
        key = _fix_case_key(issue)
        occurrence_count = max(1, int(issue.get("diagnostics", {}).get("duplicate_count", 1)))
        existing = by_key.get(key)
        if existing is None:
            grouped = dict(issue)
            grouped["occurrence_count"] = occurrence_count
            grouped["locations"] = [_issue_location(issue)]
            grouped["case_key"] = list(key)
            by_key[key] = grouped
            cases.append(grouped)
            continue
        existing["occurrence_count"] = int(existing.get("occurrence_count", 1)) + occurrence_count
        existing.setdefault("locations", []).append(_issue_location(issue))
    return cases if max_fixes < 0 else cases[:max_fixes]


def _suggestion_id(issue: dict[str, Any]) -> str:
    return ":".join(
        [
            str(issue.get("split", "")),
            str(issue.get("row_idx", "")),
            str(issue.get("field", "")),
            str(issue.get("code", "")),
        ]
    )


def _parse_suggestion(raw: str) -> tuple[str, float | None, str, str]:
    parsed = _first_json_object(raw)
    if not isinstance(parsed, dict):
        return "", None, "", "parse_error"
    suggestion = str(parsed.get("suggested_translation", "")).strip()
    confidence_value = parsed.get("confidence")
    confidence = float(confidence_value) if isinstance(confidence_value, int | float) else None
    if confidence is not None:
        confidence = max(0.0, min(1.0, confidence))
    rationale = str(parsed.get("rationale", "")).strip()
    status = "ok" if suggestion else "parse_error"
    return suggestion, confidence, rationale, status


async def _build_suggestions(
    *,
    config: EvaluateWorkflowConfigModel,
    adapter: LLMChatAdapter,
    issues: list[dict[str, Any]],
    show_progress: bool,
) -> list[dict[str, Any]]:
    evaluation = config.dataset.evaluation
    if evaluation is None:
        raise ValueError("check-translation-fix requires dataset.evaluation")
    suggestions: list[dict[str, Any]] = []
    semaphore = anyio.Semaphore(config.runtime.concurrency)

    async def process_issue(issue: dict[str, Any]) -> dict[str, Any]:
        source_text = _sample_text(issue, "source")
        translation_text = _sample_text(issue, "translation")
        user_prompt = FIX_USER_PROMPT.format(
            source_lang=evaluation.source_lang,
            target_lang=evaluation.target_lang,
            domain=evaluation.domain,
            code=issue.get("code", ""),
            message=issue.get("message", ""),
            source_text=source_text,
            translation=translation_text,
        )
        async with semaphore:
            response = await adapter.chat(
                model=config.llm.model,
                system_prompt=FIX_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                temperature=config.llm.temperature,
                max_tokens=config.runtime.max_completion_tokens,
            )
        if response.error:
            return {
                "suggestion_id": _suggestion_id(issue),
                "status": "error",
                "issue": issue,
                "source": source_text,
                "current_translation": translation_text,
                "suggested_translation": "",
                "confidence": None,
                "rationale": "",
                "raw_response": "",
                "attempts": response.attempts,
                "error": response.error,
                "usage": response.usage,
                "usage_cost": response.cost,
                "finish_reason": response.finish_reason,
            }
        suggested_translation, confidence, rationale, status = _parse_suggestion(response.content)
        return {
            "suggestion_id": _suggestion_id(issue),
            "status": status,
            "issue": issue,
            "source": source_text,
            "current_translation": translation_text,
            "suggested_translation": suggested_translation,
            "confidence": confidence,
            "rationale": rationale,
            "raw_response": response.content,
            "attempts": response.attempts,
            "error": "" if status == "ok" else "could not parse suggestion",
            "usage": response.usage,
            "usage_cost": response.cost,
            "finish_reason": response.finish_reason,
        }

    with progress_bar(total=len(issues), desc="check-translation-fix", unit="case", enabled=show_progress) as progress:
        async with anyio.create_task_group() as task_group:
            results: list[dict[str, Any] | None] = [None] * len(issues)

            async def run_one(idx: int, issue: dict[str, Any]) -> None:
                try:
                    results[idx] = await process_issue(issue)
                finally:
                    progress.update(1)

            for idx, issue in enumerate(issues):
                task_group.start_soon(run_one, idx, issue)

    suggestions = [row for row in results if row is not None]
    await adapter.close()
    return suggestions


def run_translation_quality_fix(
    *,
    dataset_id: str,
    run_name: str = "",
    config_root: str = "conf",
    overrides: list[str] | None = None,
    max_fixes: int = 50,
    show_progress: bool = False,
) -> dict[str, Any]:
    if not dataset_id:
        raise ValueError("check-translation-fix requires --dataset")
    quality_payload = run_translation_quality_check(
        dataset_id=dataset_id,
        run_name=run_name,
        config_root=config_root,
        overrides=list(overrides or []),
        max_issues=-1,
        show_progress=show_progress,
    )
    fixable_issues = _fixable_issues(quality_payload)
    issues = _group_fix_cases(fixable_issues, max_fixes)
    config = load_workflow_model(
        "evaluate",
        config_root=config_root,
        dataset_id=dataset_id,
        run_name=run_name or None,
        overrides=list(overrides or []),
    )
    if not isinstance(config, EvaluateWorkflowConfigModel):
        raise TypeError(f"expected evaluate config for {dataset_id}")
    if issues:
        adapter = build_llm_adapter(config.runtime, config.llm)
        suggestions = anyio.run(lambda: _build_suggestions(config=config, adapter=adapter, issues=issues, show_progress=show_progress))
    else:
        suggestions = []

    summary_path = Path(str(quality_payload["summary_path"]))
    report_dir = summary_path.parent
    suggestions_path = report_dir / "fix_suggestions.jsonl"
    suggestions_html_path = report_dir / "fix_suggestions.html"
    suggestions_summary_path = report_dir / "fix_suggestions_summary.json"
    payload = {
        "workflow": "check-translation-fix",
        "dataset_id": dataset_id,
        "run_name": run_name or "",
        "selected_issue_count": sum(int(issue.get("occurrence_count", 1)) for issue in issues),
        "selected_case_count": len(issues),
        "deduplicated_issue_count": sum(int(issue.get("occurrence_count", 1)) for issue in issues) - len(issues),
        "suggestion_count": len(suggestions),
        "quality_summary_path": str(summary_path),
        "suggestions_path": str(suggestions_path),
        "suggestions_html_path": str(suggestions_html_path),
        "model": config.llm.model,
        "suggestions": suggestions,
    }
    write_jsonl(suggestions_path, suggestions)
    suggestions_html_path.write_text(render_fix_suggestions_html(payload), encoding="utf-8")
    write_json_report(suggestions_summary_path, payload)
    payload["summary_path"] = str(suggestions_summary_path)
    return payload


def format_fix_summary(payload: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"check-translation-fix: {payload['dataset_id']}",
            f"selected_issues: {payload['selected_issue_count']}",
            f"selected_cases: {payload.get('selected_case_count', payload['suggestion_count'])}",
            f"suggestions: {payload['suggestion_count']}",
            f"suggestions_jsonl: {payload['suggestions_path']}",
            f"suggestions_html: {payload['suggestions_html_path']}",
        ]
    )
