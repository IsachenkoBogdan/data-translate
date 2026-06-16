from dataclasses import asdict, dataclass, field
from typing import Any


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
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualitySuppression:
    split: str
    row_idx: int | None
    field: str
    reason: str
    sample: dict[str, Any]
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class QualityReport:
    checked_rows: int
    issues: list[QualityIssue]
    checked_pairs: int = 0
    checked_rows_by_split: dict[str, int] = field(default_factory=dict)
    checked_pairs_by_split: dict[str, int] = field(default_factory=dict)
    checked_pairs_by_field: dict[str, int] = field(default_factory=dict)
    suppressed: list[QualitySuppression] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def suppressed_count(self) -> int:
        return len(self.suppressed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_rows": self.checked_rows,
            "checked_pairs": self.checked_pairs,
            "checked_rows_by_split": self.checked_rows_by_split,
            "checked_pairs_by_split": self.checked_pairs_by_split,
            "checked_pairs_by_field": self.checked_pairs_by_field,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
            "suppressed_count": self.suppressed_count,
            "issues": [issue.to_dict() for issue in self.issues],
            "suppressed": [item.to_dict() for item in self.suppressed],
        }


def short_sample(value: Any, limit: int = 300) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "..."
    return value
