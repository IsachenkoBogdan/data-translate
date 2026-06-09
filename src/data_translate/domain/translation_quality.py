import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from datasets import DatasetDict

from data_translate.domain.renderers import action_sequence
from data_translate.domain.translation_strategies.deep_map import deep_map_text_pairs
from data_translate.domain.translation_strategies.nested import nested_text_pairs


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

_URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
_EMAIL_RE = re.compile(r"(?i)\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b")
_FILE_EXTENSION_RE = re.compile(
    r"(?i)\.(?:7z|avif|bmp|csv|doc|docx|gif|gz|htm|html|jpeg|jpg|json|pdf|png|ppt|pptx|tar|tsv|txt|webp|xls|xlsx|xml|zip)\b"
)
_FILE_ATTACHMENT_RE = re.compile(
    r"(?i)^\s*`?[^()\n]{0,180}\.(?:7z|avif|bmp|csv|doc|docx|gif|gz|htm|html|jpeg|jpg|json|pdf|png|ppt|pptx|tar|tsv|txt|webp|xls|xlsx|xml|zip)\s*(?:\([^)]*\))?\s*$"
)
_BARE_PATH_RE = re.compile(r"(?i)^\s*(?:[\w.-]+/)+[\w./-]+\s*$")
_HASH_OR_ID_RE = re.compile(r"(?i)^[a-f0-9]{16,}$|^[a-z0-9_-]{24,}$")
_HASH_OR_ID_TOKEN_RE = re.compile(r"(?i)\b[a-f0-9]{16,}\b|\b[a-z0-9_-]{24,}\b")
_PATH_FRAGMENT_RE = re.compile(r"(?i)(?:/[\w.+-]+){2,}")
_HANDLE_RE = re.compile(r"(?<![\w.])@[\w.-]+")
_HTML_TAG_RE = re.compile(r"(?is)<[^>]+>")
_BACKTICK_CODE_RE = re.compile(r"(?s)```.*?```|`[^`]+`")
_LATEX_RE = re.compile(r"(?s)\$[^$]+\$")
_COMMAND_RE = re.compile(r"(?i)(?:^|\s)(?:awk|df|ffmpeg|localedef|mkfs|sudo|umount)\b")
_TECHNICAL_LABELS = {"hth", "output", "source"}


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


def _is_modelish_value(value: str) -> bool:
    parts = [part.strip("()[]{}:;,!?\"'`") for part in value.split()]
    parts = [part for part in parts if part]
    if len(parts) < 2 or len(parts) > 8:
        return False
    if not any(char.isdigit() for char in value):
        return False
    for part in parts:
        if part.isalpha() and part.islower() and part not in {"i"}:
            return False
    return True


def _is_technical_unchanged_value(value: str) -> bool:
    stripped = value.strip()
    if not stripped:
        return False
    if _URL_RE.fullmatch(stripped.strip("()[]<>\"'`")) or _EMAIL_RE.fullmatch(stripped):
        return True
    without_urls = _URL_RE.sub("", stripped)
    if without_urls and not any(char.isalnum() for char in without_urls):
        return True
    if _FILE_ATTACHMENT_RE.fullmatch(stripped):
        return True
    if _BARE_PATH_RE.fullmatch(stripped):
        return True
    if _HASH_OR_ID_RE.fullmatch(stripped):
        return True
    if _HASH_OR_ID_TOKEN_RE.search(stripped) and _PATH_FRAGMENT_RE.search(stripped):
        return True
    if _is_modelish_value(stripped):
        return True

    technical_context = bool(
        _URL_RE.search(stripped)
        or _BACKTICK_CODE_RE.search(stripped)
        or _LATEX_RE.search(stripped)
        or _COMMAND_RE.search(stripped)
        or _PATH_FRAGMENT_RE.search(stripped)
        or "<code>" in stripped.lower()
        or "<a " in stripped.lower()
        or "href=" in stripped.lower()
        or "</a>" in stripped.lower()
    )
    if _COMMAND_RE.search(stripped):
        technical_chars = sum(1 for char in stripped if not char.isalpha() and not char.isspace())
        if technical_chars / max(1, len(stripped)) >= 0.08:
            return True
    if _LATEX_RE.search(stripped) or _BACKTICK_CODE_RE.search(stripped):
        without_code = _LATEX_RE.sub("", _BACKTICK_CODE_RE.sub("", stripped))
        if not [token for token in _tokens(without_code) if token not in _TECHNICAL_LABELS]:
            return True

    tokens = _tokens(stripped)
    if not tokens:
        return True
    if technical_context:
        semantic = _URL_RE.sub("", stripped)
        semantic = _EMAIL_RE.sub("", semantic)
        semantic = _BACKTICK_CODE_RE.sub("", semantic)
        semantic = _LATEX_RE.sub("", semantic)
        semantic = _HTML_TAG_RE.sub("", semantic)
        semantic = _HANDLE_RE.sub("", semantic)
        semantic_tokens = [token for token in _tokens(semantic) if token not in _TECHNICAL_LABELS]
        if not semantic_tokens or not any(token in _ENGLISH_SIGNAL_WORDS for token in semantic_tokens):
            return True
    if _URL_RE.search(stripped) or _FILE_EXTENSION_RE.search(stripped):
        signal_tokens = [token for token in tokens if token in _ENGLISH_SIGNAL_WORDS]
        technical_chars = sum(1 for char in stripped if not char.isalpha() and not char.isspace())
        technical_ratio = technical_chars / max(1, len(stripped))
        return len(signal_tokens) <= 1 and technical_ratio >= 0.18
    return False


def suspicious_unchanged_translation(source: str, translated: str, *, min_letters: int = 12) -> bool:
    return (
        _letter_count(source) >= min_letters
        and not _is_technical_unchanged_value(source)
        and _has_english_signal(source)
        and _norm(source) == _norm(translated)
    )


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
    if strategy == "deep_map_texts":
        raw_exclude_keys = options.get("exclude_keys", [])
        if isinstance(raw_exclude_keys, str):
            exclude_keys = {raw_exclude_keys}
        elif isinstance(raw_exclude_keys, list):
            exclude_keys = {str(item) for item in raw_exclude_keys}
        else:
            exclude_keys = set()
        return deep_map_text_pairs(source_value, translated_value, exclude_keys=exclude_keys)
    if strategy == "nested_text_fields":
        return nested_text_pairs(source_value, translated_value, [str(path) for path in options.get("paths", [])])
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
