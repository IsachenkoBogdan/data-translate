from collections import defaultdict
from collections.abc import Iterable

from datasets import DatasetDict

from data_translate.domain.renderers import action_sequence
from data_translate.domain.translation_quality_checks import (
    append_repeated_translation_issues,
    check_text_pair,
    deduplicate_warning_issues,
    issue,
    record_repeated_translation_candidate,
)
from data_translate.domain.translation_quality_models import (
    QualityIssue,
    QualityReport,
    QualityRule,
    QualitySuppression,
    short_sample,
)
from data_translate.domain.translation_quality_pairs import inferred_rules, text_pairs
from data_translate.domain.translation_quality_text import suspicious_unchanged_translation
from data_translate.engine.progress import progress_bar


def _iter_common_splits(source: DatasetDict | None, translated: DatasetDict) -> Iterable[str]:
    if source is None:
        return translated.keys()
    return [split for split in source.keys() if split in translated]


def _split_limit(source_split: object, translated_split: object, max_rows_per_split: int) -> int:
    limit = min(len(source_split), len(translated_split))  # type: ignore[arg-type]
    if max_rows_per_split > 0:
        limit = min(limit, max_rows_per_split)
    return limit


def _progress_total(
    *,
    source: DatasetDict | None,
    translated: DatasetDict,
    active_rules: list[QualityRule],
    max_rows_per_split: int,
) -> int:
    total = 0
    for split in _iter_common_splits(source, translated):
        translated_split = translated[split]
        source_split = source[split] if source is not None else translated_split
        total += _split_limit(source_split, translated_split, max_rows_per_split) * max(1, len(active_rules))
    return total


def audit_translation_quality(
    *,
    source: DatasetDict | None,
    translated: DatasetDict,
    rules: list[QualityRule],
    unchanged_min_letters: int = 12,
    max_rows_per_split: int = 0,
    allowed_extra_splits: Iterable[str] | None = None,
    show_progress: bool = False,
) -> QualityReport:
    issues: list[QualityIssue] = []
    suppressed: list[QualitySuppression] = []
    checked_rows = 0
    checked_pairs = 0
    checked_rows_by_split: dict[str, int] = {}
    checked_pairs_by_split: dict[str, int] = defaultdict(int)
    checked_pairs_by_field: dict[str, int] = defaultdict(int)
    repeated_translations: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    active_rules = rules or inferred_rules(translated)
    allowed_extra = set(allowed_extra_splits or [])

    if source is not None:
        for split in source:
            if split not in translated:
                issues.append(issue("error", "split_missing", split, None, "", "translated dataset is missing source split"))
        for split in translated:
            if split not in source and split not in allowed_extra:
                issues.append(issue("warning", "split_extra", split, None, "", "translated dataset has an extra split"))

    total = _progress_total(source=source, translated=translated, active_rules=active_rules, max_rows_per_split=max_rows_per_split)
    with progress_bar(total=total, desc="check-translation", unit="row", enabled=show_progress) as progress:
        for split in _iter_common_splits(source, translated):
            translated_split = translated[split]
            source_split = source[split] if source is not None else translated_split
            limit = _split_limit(source_split, translated_split, max_rows_per_split)
            checked_rows += limit
            checked_rows_by_split[split] = limit
            if len(source_split) != len(translated_split):
                issues.append(
                    issue(
                        "error",
                        "row_count_mismatch",
                        split,
                        None,
                        "",
                        f"row count mismatch: {len(source_split)} -> {len(translated_split)}",
                    )
                )

            for rule in active_rules:
                if rule.source not in source_split.column_names:
                    issues.append(issue("error", "schema_missing_field", split, None, rule.source, "source field is missing"))
                    progress.update(limit)
                    continue
                if rule.target not in translated_split.column_names:
                    issues.append(issue("error", "schema_missing_field", split, None, rule.target, "translated field is missing"))
                    progress.update(limit)
                    continue

                options = dict(rule.options or {})
                allow_title_like = bool(options.get("allow_unchanged_title_like", False))
                for row_idx in range(limit):
                    source_value = source_split[row_idx][rule.source]
                    translated_value = translated_split[row_idx][rule.target]
                    pairs, structural_errors = text_pairs(source_value, translated_value, rule.strategy, options)
                    for structural_error in structural_errors:
                        code = "list_length_mismatch" if "length mismatch" in structural_error else "field_type_mismatch"
                        issues.append(
                            issue(
                                "error",
                                code,
                                split,
                                row_idx,
                                rule.target,
                                structural_error,
                                {"source": short_sample(source_value), "translation": short_sample(translated_value)},
                            )
                        )
                    for path, source_text, translated_text in pairs:
                        field = f"{rule.target}{path}"
                        checked_pairs += 1
                        checked_pairs_by_split[split] += 1
                        checked_pairs_by_field[field] += 1
                        check_text_pair(
                            issues=issues,
                            suppressed=suppressed,
                            split=split,
                            row_idx=row_idx,
                            field=field,
                            source_text=source_text,
                            translated_text=translated_text,
                            unchanged_min_letters=unchanged_min_letters,
                            allow_unchanged_title_like=allow_title_like,
                        )
                        if not allow_title_like:
                            record_repeated_translation_candidate(
                                repeated_translations,
                                split=split,
                                row_idx=row_idx,
                                field=field,
                                source_text=source_text,
                                translated_text=translated_text,
                            )
                    if rule.strategy == "weblinx_query" and action_sequence(str(source_value or "")) != action_sequence(str(translated_value or "")):
                        issues.append(
                            issue(
                                "error",
                                "weblinx_action_changed",
                                split,
                                row_idx,
                                rule.target,
                                "WebLINX action sequence changed",
                                {
                                    "source_actions": action_sequence(str(source_value or "")),
                                    "translation_actions": action_sequence(str(translated_value or "")),
                                },
                            )
                        )
                    progress.update(1)

    append_repeated_translation_issues(issues, repeated_translations)
    issues = deduplicate_warning_issues(issues)

    return QualityReport(
        checked_rows=checked_rows,
        issues=issues,
        checked_pairs=checked_pairs,
        checked_rows_by_split=dict(checked_rows_by_split),
        checked_pairs_by_split=dict(checked_pairs_by_split),
        checked_pairs_by_field=dict(checked_pairs_by_field),
        suppressed=suppressed,
    )
