from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from data_translate.engine.jsonl import append_jsonl, load_jsonl, write_jsonl
from data_translate.engine.reports import write_json_report


CandidateResult = tuple[dict[str, Any], list[dict[str, Any]]]
CandidateProcessor = Callable[[str, Path], CandidateResult]


def _format_candidate_exception(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {str(exc)[:300]}"


def _candidate_status_rows(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        if str(row.get("record_type", "")) != "candidate_status":
            continue
        candidate = str(row.get("candidate", "")).strip()
        if candidate:
            latest[candidate] = dict(row)
    return latest


def _candidate_attempt(status_row: dict[str, Any] | None) -> int:
    if status_row is None:
        return 1
    value = status_row.get("attempt", 0)
    return max(1, int(value) + 1) if isinstance(value, int | float) else 1


def _detail_record(candidate_name: str, row: dict[str, Any], *, attempt: int) -> dict[str, Any]:
    record = dict(row)
    record.setdefault("candidate", candidate_name)
    record.setdefault("status", "ok")
    record.setdefault("record_type", "detail")
    record["attempt"] = attempt
    return record


def _status_record(
    candidate_name: str,
    *,
    attempt: int,
    status: str,
    summary: dict[str, Any] | None = None,
    error: str = "",
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "candidate": candidate_name,
        "attempt": attempt,
        "status": status,
        "record_type": "candidate_status",
        "error": error,
    }
    if summary is not None:
        record["summary"] = summary
    return record


def _build_candidate_report(
    *,
    workflow: str,
    dataset_id: str,
    run_name: str,
    artifacts: dict[str, Any],
    summary_key: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    status_rows = _candidate_status_rows(rows)
    summaries: dict[str, Any] = {}
    errors: dict[str, Any] = {}
    for candidate_name, row in status_rows.items():
        if str(row.get("status", "")) == "ok":
            summaries[candidate_name] = row.get("summary", {})
        else:
            errors[candidate_name] = {
                "status": row.get("status", ""),
                "error": row.get("error", ""),
            }
    report = {
        "workflow": workflow,
        "dataset_id": dataset_id,
        "run_name": run_name,
        "artifacts": artifacts,
        summary_key: summaries,
    }
    if errors:
        report["errors"] = errors
    return report


def _compact_candidate_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_attempt_by_candidate = {
        candidate: int(status_row.get("attempt", 1))
        for candidate, status_row in _candidate_status_rows(rows).items()
    }
    compacted: list[dict[str, Any]] = []
    for row in rows:
        candidate = str(row.get("candidate", "")).strip()
        if not candidate:
            compacted.append(dict(row))
            continue
        latest_attempt = latest_attempt_by_candidate.get(candidate)
        if latest_attempt is None:
            continue
        attempt = row.get("attempt", 1)
        if isinstance(attempt, int | float) and int(attempt) == latest_attempt:
            compacted.append(dict(row))
    return compacted


def run_candidate_workflow(
    *,
    workflow: str,
    dataset_id: str,
    run_name: str,
    records_path: Path,
    summary_path: Path,
    artifacts: dict[str, Any],
    external_root: Path,
    selected_candidates: Iterable[str],
    candidate_paths: dict[str, str],
    summary_key: str,
    process_candidate: CandidateProcessor,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    records = load_jsonl(records_path)
    status_rows = _candidate_status_rows(records)
    for candidate_name in selected_candidates:
        existing = status_rows.get(candidate_name)
        if existing is not None and str(existing.get("status", "")) == "ok":
            continue
        attempt = _candidate_attempt(existing)
        candidate_path = external_root / candidate_paths[candidate_name]
        try:
            candidate_summary, candidate_records = process_candidate(candidate_name, candidate_path)
        except Exception as exc:
            status_record = _status_record(
                candidate_name,
                attempt=attempt,
                status="error",
                error=_format_candidate_exception(exc),
            )
            append_jsonl(records_path, [status_record])
            records.append(status_record)
            status_rows[candidate_name] = status_record
        else:
            new_rows = [
                *[_detail_record(candidate_name, row, attempt=attempt) for row in candidate_records],
                _status_record(candidate_name, attempt=attempt, status="ok", summary=candidate_summary),
            ]
            append_jsonl(records_path, new_rows)
            records.extend(new_rows)
            status_rows[candidate_name] = new_rows[-1]

    records = _compact_candidate_rows(records)
    write_jsonl(records_path, records)

    report = _build_candidate_report(
        workflow=workflow,
        dataset_id=dataset_id,
        run_name=run_name,
        artifacts=artifacts,
        summary_key=summary_key,
        rows=records,
    )
    write_json_report(summary_path, report)
    return report, records
