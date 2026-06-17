import re
from typing import Any

from data_translate.domain.translation_quality_fields import normalized_field_path
from data_translate.domain.translation_quality_models import QualityIssue, QualitySuppression, short_sample
from data_translate.domain.translation_quality_text import (
    CONTENT_HEURISTIC_MAX_ALPHA,
    ENGLISH_RESIDUE_MIN_TOKENS,
    LENGTH_RATIO_HIGH,
    LENGTH_RATIO_LOW,
    LENGTH_RATIO_MIN_ALPHA,
    REPEATED_TRANSLATION_MAX_TEXT_CHARS,
    REPEATED_TRANSLATION_MIN_DISTINCT_SOURCES,
    empty_translated,
    has_english_signal,
    html_entities,
    is_short_title_like_value,
    letter_count,
    norm_text,
    pair_diagnostics,
    technical_unchanged_reason,
)


def issue(
    severity: str,
    code: str,
    split: str,
    row_idx: int | None,
    field: str,
    message: str,
    sample: dict[str, Any] | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> QualityIssue:
    return QualityIssue(
        severity=severity,
        code=code,
        split=split,
        row_idx=row_idx,
        field=field,
        message=message,
        sample=sample or {},
        diagnostics=diagnostics or {},
    )


def suppression(
    *,
    split: str,
    row_idx: int | None,
    field: str,
    reason: str,
    source_text: str,
    translated_text: str,
    diagnostics: dict[str, Any],
) -> QualitySuppression:
    return QualitySuppression(
        split=split,
        row_idx=row_idx,
        field=field,
        reason=reason,
        sample={"source": short_sample(source_text), "translation": short_sample(translated_text)},
        diagnostics=diagnostics,
    )


def check_text_pair(
    *,
    issues: list[QualityIssue],
    suppressed: list[QualitySuppression],
    split: str,
    row_idx: int,
    field: str,
    source_text: str,
    translated_text: str,
    unchanged_min_letters: int,
    allow_unchanged_title_like: bool = False,
) -> None:
    diagnostics = pair_diagnostics(source_text, translated_text)
    sample = {"source": short_sample(source_text), "translation": short_sample(translated_text)}
    if empty_translated(source_text, translated_text):
        issues.append(
            issue(
                "error",
                "empty_translation",
                split,
                row_idx,
                field,
                "source is non-empty but translation is empty",
                sample,
                diagnostics,
            )
        )
        return

    source_is_technical = technical_unchanged_reason(source_text)
    if norm_text(source_text) and norm_text(source_text) == norm_text(translated_text):
        if source_is_technical:
            suppressed.append(
                suppression(
                    split=split,
                    row_idx=row_idx,
                    field=field,
                    reason=source_is_technical,
                    source_text=source_text,
                    translated_text=translated_text,
                    diagnostics=diagnostics,
                )
            )
            return
        if allow_unchanged_title_like and is_short_title_like_value(source_text):
            suppressed.append(
                suppression(
                    split=split,
                    row_idx=row_idx,
                    field=field,
                    reason="title_like_value",
                    source_text=source_text,
                    translated_text=translated_text,
                    diagnostics=diagnostics,
                )
            )
            return

    if letter_count(source_text) >= unchanged_min_letters and has_english_signal(source_text) and norm_text(source_text) == norm_text(translated_text):
        issues.append(
            issue(
                "warning",
                "unchanged_translation",
                split,
                row_idx,
                field,
                "meaningful English-looking source remained unchanged",
                sample,
                diagnostics,
            )
        )
        return

    if allow_unchanged_title_like:
        return

    source_alpha_count = int(diagnostics["source_alpha_count"])
    translation_alpha_count = int(diagnostics["translation_alpha_count"])
    content_heuristics_enabled = (
        source_alpha_count <= CONTENT_HEURISTIC_MAX_ALPHA
        and translation_alpha_count <= CONTENT_HEURISTIC_MAX_ALPHA * LENGTH_RATIO_HIGH
    )

    translation_entities = diagnostics["html_entities_in_translation"]
    source_entities = set(html_entities(source_text))
    if any(entity not in source_entities for entity in translation_entities):
        issues.append(
            issue(
                "warning",
                "html_entity_leak",
                split,
                row_idx,
                field,
                "HTML entity appears in translation",
                sample,
                diagnostics,
            )
        )

    if content_heuristics_enabled and diagnostics["source_markers"] and diagnostics["source_markers"] != diagnostics["translation_markers"]:
        issues.append(
            issue(
                "warning",
                "placeholder_or_marker_changed",
                split,
                row_idx,
                field,
                "placeholder or markup-like marker changed between source and translation",
                sample,
                diagnostics,
            )
        )

    ratio = diagnostics["length_ratio"]
    if (
        ratio is not None
        and source_alpha_count >= LENGTH_RATIO_MIN_ALPHA
        and translation_alpha_count > 0
        and not source_is_technical
        and not (allow_unchanged_title_like and is_short_title_like_value(source_text))
    ):
        if ratio < LENGTH_RATIO_LOW:
            issues.append(
                issue(
                    "warning",
                    "length_ratio_low",
                    split,
                    row_idx,
                    field,
                    "translation is much shorter than source",
                    sample,
                    diagnostics,
                )
            )
        elif ratio > LENGTH_RATIO_HIGH:
            issues.append(
                issue(
                    "warning",
                    "length_ratio_high",
                    split,
                    row_idx,
                    field,
                    "translation is much longer than source",
                    sample,
                    diagnostics,
                )
            )

    if (
        translated_text.strip()
        and norm_text(source_text) != norm_text(translated_text)
        and content_heuristics_enabled
        and translation_alpha_count >= LENGTH_RATIO_MIN_ALPHA
        and int(diagnostics["english_signal_token_count_in_translation"]) >= ENGLISH_RESIDUE_MIN_TOKENS
        and not source_is_technical
        and not (allow_unchanged_title_like and is_short_title_like_value(translated_text))
    ):
        issues.append(
            issue(
                "warning",
                "english_residue",
                split,
                row_idx,
                field,
                "translation still contains several English signal words",
                sample,
                diagnostics,
            )
        )


def repeated_translation_key(field: str, translated_text: str) -> tuple[str, str]:
    root_field = re.split(r"[\[.]", field, maxsplit=1)[0]
    return root_field, norm_text(translated_text)


def record_repeated_translation_candidate(
    repeated_translations: dict[tuple[str, str], list[dict[str, Any]]],
    *,
    split: str,
    row_idx: int,
    field: str,
    source_text: str,
    translated_text: str,
) -> None:
    if len(source_text) > REPEATED_TRANSLATION_MAX_TEXT_CHARS or len(translated_text) > REPEATED_TRANSLATION_MAX_TEXT_CHARS:
        return
    if letter_count(source_text) < LENGTH_RATIO_MIN_ALPHA or letter_count(translated_text) < LENGTH_RATIO_MIN_ALPHA:
        return
    if norm_text(source_text) == norm_text(translated_text) or technical_unchanged_reason(source_text):
        return
    key = repeated_translation_key(field, translated_text)
    if not key[1]:
        return
    repeated_translations[key].append(
        {
            "split": split,
            "row_idx": row_idx,
            "field": field,
            "source": source_text,
            "translation": translated_text,
        }
    )


def append_repeated_translation_issues(
    issues: list[QualityIssue],
    repeated_translations: dict[tuple[str, str], list[dict[str, Any]]],
) -> None:
    for (root_field, _translation_norm), rows in repeated_translations.items():
        distinct_sources: dict[str, dict[str, Any]] = {}
        for row in rows:
            distinct_sources.setdefault(norm_text(str(row["source"])), row)
        if len(distinct_sources) < REPEATED_TRANSLATION_MIN_DISTINCT_SOURCES:
            continue
        first = rows[0]
        examples = list(distinct_sources.values())[:5]
        fields = {normalized_field_path(str(row.get("field", ""))) for row in rows if row.get("field")}
        issue_field = next(iter(fields)) if len(fields) == 1 else root_field
        issues.append(
            issue(
                "warning",
                "repeated_translation",
                str(first["split"]),
                int(first["row_idx"]),
                issue_field,
                "same translation is reused for several distinct source texts",
                {
                    "translation": short_sample(first["translation"]),
                    "distinct_source_count": len(distinct_sources),
                    "examples": [
                        {
                            "split": item["split"],
                            "row_idx": item["row_idx"],
                            "field": item["field"],
                            "source": short_sample(item["source"], limit=180),
                        }
                        for item in examples
                    ],
                },
                {
                    "distinct_source_count": len(distinct_sources),
                    "occurrence_count": len(rows),
                },
            )
        )


def deduplicate_warning_issues(issues: list[QualityIssue]) -> list[QualityIssue]:
    deduped: list[QualityIssue] = []
    seen: dict[tuple[str, str, str, str, str], QualityIssue] = {}
    for current_issue in issues:
        sample = current_issue.sample
        source = sample.get("source")
        translation = sample.get("translation")
        if current_issue.severity != "warning" or not isinstance(source, str) or not isinstance(translation, str):
            deduped.append(current_issue)
            continue
        key = (current_issue.code, current_issue.field, current_issue.message, source, translation)
        existing = seen.get(key)
        if existing is not None:
            existing.diagnostics["duplicate_count"] = int(existing.diagnostics.get("duplicate_count", 1)) + 1
            continue
        current_issue.diagnostics.setdefault("duplicate_count", 1)
        seen[key] = current_issue
        deduped.append(current_issue)
    return deduped
