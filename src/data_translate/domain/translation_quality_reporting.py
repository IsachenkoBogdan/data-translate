from collections import Counter, defaultdict
from typing import Any

from data_translate.domain.translation_quality_fields import field_group_position_summary, normalized_field_path, root_field
from data_translate.domain.translation_quality_html import render_fix_suggestions_html, render_quality_html


ISSUE_GUIDANCE: dict[str, dict[str, str]] = {
    "row_count_mismatch": {
        "rule": "Row count mismatch",
        "priority": "fix",
        "label": "Fix before upload",
        "meaning": "Source and translated split have different row counts.",
        "action": "Regenerate or repair the translated artifact; row alignment is broken.",
    },
    "split_missing": {
        "rule": "Missing split",
        "priority": "fix",
        "label": "Fix before upload",
        "meaning": "A source split is missing from the translated dataset.",
        "action": "Check dataset config and export path.",
    },
    "schema_missing_field": {
        "rule": "Missing field",
        "priority": "fix",
        "label": "Fix before upload",
        "meaning": "A source or translated field required by the config is missing.",
        "action": "Fix the config or materialized dataset schema.",
    },
    "list_length_mismatch": {
        "rule": "List length mismatch",
        "priority": "fix",
        "label": "Fix before upload",
        "meaning": "A translated list no longer has the same number of items.",
        "action": "Repair the affected row; nested dialogue alignment may be broken.",
    },
    "field_type_mismatch": {
        "rule": "Field type mismatch",
        "priority": "fix",
        "label": "Fix before upload",
        "meaning": "Source and translated values have incompatible structures.",
        "action": "Repair the row or adjust the translation strategy.",
    },
    "empty_translation": {
        "rule": "Empty field",
        "priority": "fix",
        "label": "Fix before upload",
        "meaning": "A non-empty source text became empty after translation.",
        "action": "Re-translate or manually fill the affected text.",
    },
    "weblinx_action_changed": {
        "rule": "WebLINX action changed",
        "priority": "fix",
        "label": "Fix before upload",
        "meaning": "WebLINX action syntax changed during translation.",
        "action": "Restore action sequence exactly; only natural language should change.",
    },
    "unchanged_translation": {
        "rule": "Unchanged English text",
        "priority": "review",
        "label": "Review",
        "meaning": "English-looking text stayed unchanged.",
        "action": "Usually fix unless it is a name, title, URL, code, or other intentional technical value.",
    },
    "english_residue": {
        "rule": "English residue",
        "priority": "review",
        "label": "Review",
        "meaning": "Several English signal words remain in the translated text.",
        "action": "Inspect examples; this often catches partially untranslated fragments.",
    },
    "digit_sequence_changed": {
        "rule": "Number changed",
        "priority": "sample",
        "label": "Sample audit",
        "meaning": "Numbers differ after translation.",
        "action": "Review a sample. Some are formatting differences, but this catches hallucinated counts, dates, and IDs.",
    },
    "placeholder_or_marker_changed": {
        "rule": "Placeholder changed",
        "priority": "review",
        "label": "Review",
        "meaning": "Markup-like placeholders or bracketed markers changed.",
        "action": "Fix if the marker is structural; ignore only if it was natural text, not syntax.",
    },
    "html_entity_leak": {
        "rule": "HTML entity leak",
        "priority": "review",
        "label": "Review",
        "meaning": "HTML entity appears in translation where it was not present in source.",
        "action": "Decode or repair if the entity is visible user-facing text.",
    },
    "length_ratio_low": {
        "rule": "Translation too short",
        "priority": "sample",
        "label": "Sample audit",
        "meaning": "Translation is much shorter than source.",
        "action": "Review examples for truncation; short paraphrases can be legitimate.",
    },
    "length_ratio_high": {
        "rule": "Translation too long",
        "priority": "sample",
        "label": "Sample audit",
        "meaning": "Translation is much longer than source.",
        "action": "Review examples for duplicated or expanded text; long translations can be legitimate.",
    },
    "repeated_translation": {
        "rule": "Repeated translation",
        "priority": "sample",
        "label": "Sample audit",
        "meaning": "Same translation appears for several distinct source texts.",
        "action": "Inspect clusters; repeated short answers may be normal, broad collapse is suspicious.",
    },
    "split_extra": {
        "rule": "Extra split",
        "priority": "sample",
        "label": "Check config",
        "meaning": "Translated dataset has an extra split.",
        "action": "Verify this split is intentional or listed as passthrough.",
    },
}

def quality_verdict(payload: dict[str, Any]) -> str:
    if int(payload.get("error_count", 0)) > 0:
        return "fail"
    if int(payload.get("warning_count", 0)) > 0:
        return "pass_with_warnings"
    return "pass"


def _counter_dict(counter: Counter[str]) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def _issue_counters(issues: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    by_severity: Counter[str] = Counter()
    by_code: Counter[str] = Counter()
    by_split: Counter[str] = Counter()
    by_field: Counter[str] = Counter()
    by_root_field: Counter[str] = Counter()
    for issue in issues:
        by_severity[str(issue.get("severity", ""))] += 1
        by_code[str(issue.get("code", ""))] += 1
        by_split[str(issue.get("split", ""))] += 1
        field = normalized_field_path(str(issue.get("field", "")))
        by_field[field] += 1
        by_root_field[root_field(field)] += 1
    return {
        "by_severity": _counter_dict(by_severity),
        "by_code": _counter_dict(by_code),
        "by_split": _counter_dict(by_split),
        "by_field": _counter_dict(by_field),
        "by_root_field": _counter_dict(by_root_field),
    }


def _field_rows(payload: dict[str, Any], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checked_by_field = {str(key): int(value) for key, value in payload.get("checked_pairs_by_field", {}).items()}
    counters: dict[str, Counter[str]] = defaultdict(Counter)
    severity_counters: dict[str, Counter[str]] = defaultdict(Counter)
    checked_by_group: dict[str, int] = defaultdict(int)
    exact_fields_by_group: dict[str, set[str]] = defaultdict(set)
    for field, count in checked_by_field.items():
        group = normalized_field_path(field)
        checked_by_group[group] += count
        exact_fields_by_group[group].add(field)
    for issue in issues:
        exact_field = str(issue.get("field", ""))
        field = normalized_field_path(exact_field)
        exact_fields_by_group[field].add(exact_field)
        counters[field][str(issue.get("code", ""))] += 1
        severity_counters[field][str(issue.get("severity", ""))] += 1

    rows = []
    for field in sorted(set(checked_by_group) | set(counters)):
        checked = checked_by_group.get(field, 0)
        errors = severity_counters[field].get("error", 0)
        warnings = severity_counters[field].get("warning", 0)
        total = errors + warnings
        exact_fields = exact_fields_by_group[field]
        rows.append(
            {
                "field": field,
                "root_field": root_field(field),
                "exact_field_count": len(exact_fields),
                "position_summary": field_group_position_summary(exact_fields),
                "checked_pairs": checked,
                "errors": errors,
                "warnings": warnings,
                "issue_rate": total / checked if checked else None,
                "warning_rate": warnings / checked if checked else None,
                "error_rate": errors / checked if checked else None,
                "top_codes": _counter_dict(counters[field]),
            }
        )
    return sorted(rows, key=lambda row: (-(row["errors"] + row["warnings"]), row["field"]))


def _split_rows(payload: dict[str, Any], issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checked_pairs_by_split = {str(key): int(value) for key, value in payload.get("checked_pairs_by_split", {}).items()}
    checked_rows_by_split = {str(key): int(value) for key, value in payload.get("checked_rows_by_split", {}).items()}
    split_sizes = {str(key): int(value) for key, value in payload.get("splits", {}).items()}
    severity_counters: dict[str, Counter[str]] = defaultdict(Counter)
    code_counters: dict[str, Counter[str]] = defaultdict(Counter)
    for issue in issues:
        split = str(issue.get("split", ""))
        severity_counters[split][str(issue.get("severity", ""))] += 1
        code_counters[split][str(issue.get("code", ""))] += 1

    rows = []
    for split in sorted(set(checked_pairs_by_split) | set(checked_rows_by_split) | set(severity_counters)):
        checked_pairs = checked_pairs_by_split.get(split, 0)
        checked_rows = checked_rows_by_split.get(split, 0)
        errors = severity_counters[split].get("error", 0)
        warnings = severity_counters[split].get("warning", 0)
        total = errors + warnings
        if checked_rows == 0 and checked_pairs == 0 and total == 0:
            continue
        rows.append(
            {
                "split": split,
                "rows": split_sizes.get(split, 0),
                "checked_rows": checked_rows,
                "checked_pairs": checked_pairs,
                "errors": errors,
                "warnings": warnings,
                "issue_rate": total / checked_pairs if checked_pairs else None,
                "top_codes": _counter_dict(code_counters[split]),
            }
        )
    return sorted(rows, key=lambda row: (-(row["errors"] + row["warnings"]), row["split"]))


def _recommendation(payload: dict[str, Any]) -> dict[str, Any]:
    errors = int(payload.get("error_count", 0))
    warnings = int(payload.get("warning_count", 0))
    checked_pairs = int(payload.get("checked_pairs", 0))
    warning_rate = warnings / checked_pairs if checked_pairs else 0.0
    if errors:
        return {
            "level": "block",
            "summary": "Fix errors before upload.",
            "detail": "Structural errors can break row alignment, schema compatibility, or task semantics.",
        }
    if not warnings:
        return {
            "level": "pass",
            "summary": "Ready for upload.",
            "detail": "No errors or warnings were found by the static checks.",
        }
    if warning_rate < 0.001:
        return {
            "level": "sample",
            "summary": "Upload is not blocked; sample the warnings.",
            "detail": "Warnings are rare. Review the top warning codes and a few examples before spending time on manual fixes.",
        }
    return {
        "level": "review",
        "summary": "Review warnings before upload.",
        "detail": "Warning density is high enough that a short manual audit is worth doing.",
    }


def _issue_guide_rows(issue_counts: dict[str, int]) -> list[dict[str, Any]]:
    rows = []
    for code, count in issue_counts.items():
        guidance = ISSUE_GUIDANCE.get(
            code,
            {
                "rule": code.replace("_", " ").title(),
                "priority": "sample",
                "label": "Review",
                "meaning": "No specific guidance is registered for this issue code.",
                "action": "Inspect examples and decide whether this should be fixed or encoded as a normal rule.",
            },
        )
        rows.append({"code": code, "count": count, **guidance})
    priority_order = {"fix": 0, "review": 1, "sample": 2}
    return sorted(rows, key=lambda row: (priority_order.get(str(row["priority"]), 3), -int(row["count"]), str(row["code"])))


def build_quality_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    issues = [dict(issue) for issue in payload.get("issues", [])]
    issue_counts = _issue_counters(issues)
    return {
        "verdict": quality_verdict(payload),
        "checked_rows": int(payload.get("checked_rows", 0)),
        "checked_pairs": int(payload.get("checked_pairs", 0)),
        "error_count": int(payload.get("error_count", 0)),
        "warning_count": int(payload.get("warning_count", 0)),
        "rates": {
            "error_rate": int(payload.get("error_count", 0)) / int(payload.get("checked_pairs", 1) or 1),
            "warning_rate": int(payload.get("warning_count", 0)) / int(payload.get("checked_pairs", 1) or 1),
            "issue_rate": (int(payload.get("error_count", 0)) + int(payload.get("warning_count", 0))) / int(payload.get("checked_pairs", 1) or 1),
        },
        "recommendation": _recommendation(payload),
        "issue_counts": issue_counts,
        "issue_guide": _issue_guide_rows(issue_counts["by_code"]),
        "fields": _field_rows(payload, issues),
        "splits": _split_rows(payload, issues),
    }
