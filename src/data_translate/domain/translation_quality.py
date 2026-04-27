import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from datasets import DatasetDict

from data_translate.domain.renderers import action_sequence


@dataclass(frozen=True)
class QualityRule:
    source: str
    target: str
    strategy: str
    options: dict[str, Any] | None = None


@dataclass(frozen=True)
class QualityIssue:
    severity: str
    code: str
    split: str
    row_idx: int | None
    field: str
    message: str
    sample: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualityReport:
    checked_rows: int
    issues: list[QualityIssue]

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_rows": self.checked_rows,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


_ENGLISH_SIGNAL_WORDS = {
    "a",
    "am",
    "an",
    "and",
    "are",
    "be",
    "can",
    "could",
    "do",
    "does",
    "for",
    "have",
    "how",
    "i",
    "is",
    "it",
    "may",
    "my",
    "need",
    "not",
    "of",
    "offer",
    "on",
    "please",
    "should",
    "that",
    "the",
    "then",
    "this",
    "to",
    "try",
    "we",
    "what",
    "where",
    "will",
    "with",
    "you",
    "your",
}


def _norm(value: str) -> str:
    return "".join(char.lower() for char in value if char.isalnum())


def _tokens(value: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in value.lower():
        if char.isalpha() or char == "'":
            current.append(char)
        elif current:
            tokens.append("".join(current).strip("'"))
            current = []
    if current:
        tokens.append("".join(current).strip("'"))
    return [token for token in tokens if token]


def _letter_count(value: str) -> int:
    return sum(1 for char in value if char.isalpha())


def _has_english_signal(value: str) -> bool:
    return any(token in _ENGLISH_SIGNAL_WORDS for token in _tokens(value))


def suspicious_unchanged_translation(source: str, translated: str, *, min_letters: int = 12) -> bool:
    return _letter_count(source) >= min_letters and _has_english_signal(source) and _norm(source) == _norm(translated)


def _issue(
    severity: str,
    code: str,
    split: str,
    row_idx: int | None,
    field: str,
    message: str,
    sample: dict[str, Any] | None = None,
) -> QualityIssue:
    return QualityIssue(
        severity=severity,
        code=code,
        split=split,
        row_idx=row_idx,
        field=field,
        message=message,
        sample=sample or {},
    )


def _short(value: Any, limit: int = 300) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "..."
    return value


def _empty_translated(source: str, translated: str) -> bool:
    return bool(source.strip()) and not translated.strip()


def _text_pairs(source_value: Any, translated_value: Any, strategy: str, options: dict[str, Any]) -> tuple[list[tuple[str, str, str]], list[str]]:
    if strategy == "serialized_dialog_turns_content":
        return _serialized_dialog_pairs(source_value, translated_value, options)
    if strategy == "dialog_turns_content":
        return _dialog_pairs(source_value, translated_value, options)
    if isinstance(source_value, list) or isinstance(translated_value, list):
        return _list_pairs(source_value, translated_value)
    return [("", str(source_value or ""), str(translated_value or ""))], []


def _list_pairs(source_value: Any, translated_value: Any) -> tuple[list[tuple[str, str, str]], list[str]]:
    if not isinstance(source_value, list) or not isinstance(translated_value, list):
        return [], [f"type mismatch: {type(source_value).__name__} -> {type(translated_value).__name__}"]
    pairs = [
        (f"[{idx}]", str(source_item or ""), str(translated_item or ""))
        for idx, (source_item, translated_item) in enumerate(zip(source_value, translated_value, strict=False))
    ]
    errors = []
    if len(source_value) != len(translated_value):
        errors.append(f"length mismatch: {len(source_value)} -> {len(translated_value)}")
    return pairs, errors


def _dialog_pairs(source_value: Any, translated_value: Any, options: dict[str, Any]) -> tuple[list[tuple[str, str, str]], list[str]]:
    content_field = str(options.get("content_field", "content"))
    if not isinstance(source_value, list) or not isinstance(translated_value, list):
        return [], [f"type mismatch: {type(source_value).__name__} -> {type(translated_value).__name__}"]
    pairs: list[tuple[str, str, str]] = []
    for idx, (source_turn, translated_turn) in enumerate(zip(source_value, translated_value, strict=False)):
        if isinstance(source_turn, dict):
            source_text = source_turn.get(content_field, "")
        else:
            source_text = source_turn
        if isinstance(translated_turn, dict):
            translated_text = translated_turn.get(content_field, "")
        else:
            translated_text = translated_turn
        pairs.append((f"[{idx}].{content_field}", str(source_text or ""), str(translated_text or "")))
    errors = []
    if len(source_value) != len(translated_value):
        errors.append(f"length mismatch: {len(source_value)} -> {len(translated_value)}")
    return pairs, errors


def _serialized_dialog_pairs(source_value: Any, translated_value: Any, options: dict[str, Any]) -> tuple[list[tuple[str, str, str]], list[str]]:
    content_field = str(options.get("content_field", "content"))
    target_content_field = str(options.get("target_content_field", content_field))
    try:
        source_payload = json.loads(str(source_value or "[]"))
        translated_payload = json.loads(str(translated_value or "[]"))
    except json.JSONDecodeError as exc:
        return [], [f"json parse failed: {exc}"]
    if not isinstance(source_payload, list) or not isinstance(translated_payload, list):
        return [], ["serialized value must decode to lists"]
    pairs: list[tuple[str, str, str]] = []
    for idx, (source_turn, translated_turn) in enumerate(zip(source_payload, translated_payload, strict=False)):
        if not isinstance(source_turn, dict) or not isinstance(translated_turn, dict):
            continue
        pairs.append(
            (
                f"[{idx}].{target_content_field}",
                str(source_turn.get(content_field, "") or ""),
                str(translated_turn.get(target_content_field, "") or ""),
            )
        )
    errors = []
    if len(source_payload) != len(translated_payload):
        errors.append(f"length mismatch: {len(source_payload)} -> {len(translated_payload)}")
    return pairs, errors


def _inferred_rules(translated: DatasetDict) -> list[QualityRule]:
    rules: dict[tuple[str, str], QualityRule] = {}
    for split_dataset in translated.values():
        columns = set(split_dataset.column_names)
        for column in columns:
            if not column.endswith("_fr"):
                continue
            source = column.removesuffix("_fr")
            if source in columns:
                rules[(source, column)] = QualityRule(source=source, target=column, strategy="auto")
    return list(rules.values())


def _check_text_pair(
    *,
    issues: list[QualityIssue],
    split: str,
    row_idx: int,
    field: str,
    source_text: str,
    translated_text: str,
    unchanged_min_letters: int,
) -> None:
    if _empty_translated(source_text, translated_text):
        issues.append(
            _issue(
                "error",
                "empty_translation",
                split,
                row_idx,
                field,
                "source is non-empty but translation is empty",
                {"source": _short(source_text), "translation": _short(translated_text)},
            )
        )
    if suspicious_unchanged_translation(source_text, translated_text, min_letters=unchanged_min_letters):
        issues.append(
            _issue(
                "warning",
                "unchanged_translation",
                split,
                row_idx,
                field,
                "meaningful English-looking source remained unchanged",
                {"source": _short(source_text), "translation": _short(translated_text)},
            )
        )


def _iter_common_splits(source: DatasetDict | None, translated: DatasetDict) -> Iterable[str]:
    if source is None:
        return translated.keys()
    return [split for split in source.keys() if split in translated]


def audit_translation_quality(
    *,
    source: DatasetDict | None,
    translated: DatasetDict,
    rules: list[QualityRule],
    unchanged_min_letters: int = 12,
    max_rows_per_split: int = 0,
    allowed_extra_splits: Iterable[str] | None = None,
) -> QualityReport:
    issues: list[QualityIssue] = []
    checked_rows = 0
    active_rules = rules or _inferred_rules(translated)
    allowed_extra = set(allowed_extra_splits or [])

    if source is not None:
        for split in source:
            if split not in translated:
                issues.append(_issue("error", "split_missing", split, None, "", "translated dataset is missing source split"))
        for split in translated:
            if split not in source and split not in allowed_extra:
                issues.append(_issue("warning", "split_extra", split, None, "", "translated dataset has an extra split"))

    for split in _iter_common_splits(source, translated):
        translated_split = translated[split]
        source_split = source[split] if source is not None else translated_split
        limit = min(len(source_split), len(translated_split))
        if max_rows_per_split > 0:
            limit = min(limit, max_rows_per_split)
        checked_rows += limit
        if len(source_split) != len(translated_split):
            issues.append(
                _issue(
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
                issues.append(_issue("error", "schema_missing_field", split, None, rule.source, "source field is missing"))
                continue
            if rule.target not in translated_split.column_names:
                issues.append(_issue("error", "schema_missing_field", split, None, rule.target, "translated field is missing"))
                continue

            options = dict(rule.options or {})
            for row_idx in range(limit):
                source_value = source_split[row_idx][rule.source]
                translated_value = translated_split[row_idx][rule.target]
                pairs, structural_errors = _text_pairs(source_value, translated_value, rule.strategy, options)
                for structural_error in structural_errors:
                    code = "list_length_mismatch" if "length mismatch" in structural_error else "field_type_mismatch"
                    issues.append(
                        _issue(
                            "error",
                            code,
                            split,
                            row_idx,
                            rule.target,
                            structural_error,
                            {"source": _short(source_value), "translation": _short(translated_value)},
                        )
                    )
                for path, source_text, translated_text in pairs:
                    _check_text_pair(
                        issues=issues,
                        split=split,
                        row_idx=row_idx,
                        field=f"{rule.target}{path}",
                        source_text=source_text,
                        translated_text=translated_text,
                        unchanged_min_letters=unchanged_min_letters,
                    )
                if rule.strategy == "weblinx_query" and action_sequence(str(source_value or "")) != action_sequence(str(translated_value or "")):
                    issues.append(
                        _issue(
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

    return QualityReport(checked_rows=checked_rows, issues=issues)
