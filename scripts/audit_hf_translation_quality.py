import argparse
import ast
import csv
import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from urllib.parse import quote

import httpx
import pandas as pd

from data_translate.domain.translation_quality_checks import check_text_pair
from data_translate.domain.translation_quality_pairs import text_pairs


AUDITABLE_MODES = {"self_suffix", "source_compare"}
STRUCTURAL_SKIP_KEYS = {
    "id",
    "idx",
    "name",
    "role",
    "turn_id",
    "span_start",
    "span_end",
    "doc_id",
}


def endpoint(name: str, **params: str) -> str:
    query = "&".join(f"{key}={quote(str(value), safe='')}" for key, value in params.items())
    return f"https://datasets-server.huggingface.co/{name}?{query}"


class ParquetReader:
    def __init__(self, cache_dir: Path, retries: int = 3) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        timeout = httpx.Timeout(connect=30, read=300, write=30, pool=30)
        self.client = httpx.Client(timeout=timeout, follow_redirects=True)
        self.retries = retries
        self.parquet_cache: dict[tuple[str, str, str], list[str]] = {}

    def get(self, url: str) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = self.client.get(url)
                response.raise_for_status()
                return response
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(2 * attempt)
        assert last_error is not None
        raise last_error

    def parquet_files(self, repo: str, config: str, split: str) -> list[str]:
        key = (repo, config, split)
        if key in self.parquet_cache:
            return self.parquet_cache[key]
        response = self.get(endpoint("parquet", dataset=repo))
        files = [
            item["url"]
            for item in response.json().get("parquet_files", [])
            if item.get("config") == config and item.get("split") == split
        ]
        if not files:
            raise RuntimeError(f"no parquet files for {repo} {config}/{split}")
        self.parquet_cache[key] = files
        return files

    def local_file(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        path = self.cache_dir / f"{digest}.parquet"
        if path.exists() and path.stat().st_size > 0:
            return path
        tmp = path.with_suffix(".tmp")
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                if tmp.exists():
                    tmp.unlink()
                with self.client.stream("GET", url) as response:
                    response.raise_for_status()
                    with tmp.open("wb") as file:
                        for chunk in response.iter_bytes():
                            file.write(chunk)
                tmp.replace(path)
                return path
            except (httpx.HTTPError, httpx.TimeoutException, OSError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(2 * attempt)
        if tmp.exists():
            tmp.unlink()
        assert last_error is not None
        raise last_error

    def read_columns(self, repo: str, config: str, split: str, columns: list[str]) -> pd.DataFrame:
        frames = []
        for url in self.parquet_files(repo, config, split):
            local_path = self.local_file(url)
            frames.append(pd.read_parquet(local_path, columns=sorted(set(columns))))
        if len(frames) == 1:
            return frames[0]
        return pd.concat(frames, ignore_index=True)


def normalize_value(value):
    if value is None:
        return ""
    try:
        if pd.isna(value) and not isinstance(value, (list, tuple, dict)):
            return ""
    except Exception:
        pass
    if hasattr(value, "tolist") and not isinstance(value, (str, bytes, dict)):
        value = value.tolist()
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("[", "{")):
            for parser in (json.loads, ast.literal_eval):
                try:
                    return normalize_value(parser(stripped))
                except (ValueError, SyntaxError, TypeError, json.JSONDecodeError):
                    pass
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): normalize_value(item) for key, item in value.items()}
    return value


def serialized_dialog_options(source_value, translated_value, lang: str) -> dict[str, str] | None:
    if not isinstance(source_value, str) or not isinstance(translated_value, str):
        return None
    if not source_value.lstrip().startswith("[") or not translated_value.lstrip().startswith("["):
        return None
    try:
        source_payload = json.loads(source_value)
        translated_payload = json.loads(translated_value)
    except json.JSONDecodeError:
        return None
    if not isinstance(source_payload, list) or not isinstance(translated_payload, list):
        return None
    if not any(isinstance(item, dict) and "content" in item for item in source_payload):
        return None
    if not any(isinstance(item, dict) and "content" in item for item in translated_payload):
        return None
    lang_content_field = f"content_{lang}"
    target_content_field = (
        lang_content_field
        if any(isinstance(item, dict) and lang_content_field in item for item in translated_payload)
        else "content"
    )
    return {"content_field": "content", "target_content_field": target_content_field}


def strategy_for(source_value, translated_value, lang: str) -> tuple[str, dict[str, str]]:
    serialized_options = serialized_dialog_options(source_value, translated_value, lang)
    if serialized_options is not None:
        return "serialized_dialog_turns_content", serialized_options

    source_value = normalize_value(source_value)
    translated_value = normalize_value(translated_value)

    def turn_content_field(value) -> str | None:
        if not isinstance(value, list):
            return None
        for field in ("content", "message"):
            if any(isinstance(item, dict) and field in item for item in value):
                return field
        return None

    source_turn_field = turn_content_field(source_value)
    target_turn_field = turn_content_field(translated_value)
    if source_turn_field and target_turn_field and source_turn_field == target_turn_field:
        return "dialog_turns_content", {"content_field": source_turn_field}
    return "auto", {}


def append_path(path: str, part: str) -> str:
    return f"{path}.{part}" if path else part


def append_index(path: str, index: int) -> str:
    return f"{path}[{index}]" if path else f"[{index}]"


def translated_key_for(source_key: str, translated_value: dict, lang: str) -> str | None:
    suffixed = f"{source_key}_{lang}"
    if suffixed in translated_value:
        return suffixed
    if source_key in translated_value:
        return source_key
    return None


def structured_text_pairs(source_value, translated_value, lang: str, path: str = "") -> tuple[list[tuple[str, str, str]], list[str]] | None:
    if isinstance(source_value, dict) or isinstance(translated_value, dict):
        if not isinstance(source_value, dict) or not isinstance(translated_value, dict):
            return [], [f"type mismatch: {type(source_value).__name__} -> {type(translated_value).__name__}"]
        pairs: list[tuple[str, str, str]] = []
        errors: list[str] = []
        for key, source_item in source_value.items():
            source_key = str(key)
            if source_key in STRUCTURAL_SKIP_KEYS:
                continue
            target_key = translated_key_for(source_key, translated_value, lang)
            if target_key is None:
                if isinstance(source_item, str) and source_item.strip():
                    errors.append(f"missing translated text at {append_path(path, source_key)}")
                continue
            target_item = translated_value[target_key]
            item_path = append_path(path, target_key)
            nested = structured_text_pairs(source_item, target_item, lang, item_path)
            if nested is None:
                if isinstance(source_item, str) or isinstance(target_item, str):
                    pairs.append((item_path, str(source_item or ""), str(target_item or "")))
                continue
            nested_pairs, nested_errors = nested
            pairs.extend(nested_pairs)
            errors.extend(nested_errors)
        return pairs, errors

    if isinstance(source_value, list) or isinstance(translated_value, list):
        if not isinstance(source_value, list) or not isinstance(translated_value, list):
            return [], [f"type mismatch: {type(source_value).__name__} -> {type(translated_value).__name__}"]
        pairs: list[tuple[str, str, str]] = []
        errors: list[str] = []
        if len(source_value) != len(translated_value):
            errors.append(f"length mismatch: {len(source_value)} -> {len(translated_value)}")
        for idx, (source_item, target_item) in enumerate(zip(source_value, translated_value, strict=False)):
            item_path = append_index(path, idx)
            nested = structured_text_pairs(source_item, target_item, lang, item_path)
            if nested is None:
                pairs.append((item_path, str(source_item or ""), str(target_item or "")))
                continue
            nested_pairs, nested_errors = nested
            pairs.extend(nested_pairs)
            errors.extend(nested_errors)
        return pairs, errors
    return None


def audit_text_pairs(source_value, translated_value, lang: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    source_value = normalize_value(source_value)
    translated_value = normalize_value(translated_value)
    structured = structured_text_pairs(source_value, translated_value, lang)
    if structured is not None:
        return structured
    strategy, options = strategy_for(source_value, translated_value, lang)
    return text_pairs(source_value, translated_value, strategy, options)


def allow_title_like(field: str) -> bool:
    lower = field.lower()
    return any(token in lower for token in ["title", "topic", "entity", "name"])


def parse_pairs(value: str) -> list[tuple[str, str]]:
    pairs = []
    for part in value.split(";"):
        part = part.strip()
        if not part or "->" not in part:
            continue
        source, target = part.split("->", maxsplit=1)
        pairs.append((source.strip(), target.strip()))
    return pairs


def read_existing_tasks(path: Path) -> set[tuple[str, ...]]:
    if not path.exists():
        return set()
    completed = set()
    with path.open(encoding="utf-8") as file:
        for line in file:
            row = json.loads(line)
            if row.get("status") not in {"ok", "missing_split"}:
                continue
            completed.add(
                (
                    row.get("dataset", ""),
                    row.get("lang", ""),
                    row.get("target_repo", ""),
                    row.get("target_config", ""),
                    row.get("target_split", ""),
                )
            )
    return completed


def task_key(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row.get("dataset", ""),
        row.get("lang", ""),
        row.get("target_repo", ""),
        row.get("target_config", ""),
        row.get("target_split", ""),
        row.get("mode", ""),
        row.get("pairs", ""),
        row.get("source_repo", ""),
        row.get("source_config", ""),
        row.get("source_split", ""),
    )


def parse_exclusions(values: list[str]) -> set[tuple[str, str]]:
    exclusions = set()
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            if ":" not in item:
                raise ValueError(f"expected DATASET:LANG exclusion, got {item!r}")
            dataset, lang = item.split(":", maxsplit=1)
            exclusions.add((dataset.strip(), lang.strip()))
    return exclusions


def apply_exclusions(plan_rows: list[dict[str, str]], exclusions: set[tuple[str, str]]) -> list[dict[str, str]]:
    if not exclusions:
        return plan_rows
    updated = []
    for row in plan_rows:
        if (row.get("dataset", ""), row.get("lang", "")) not in exclusions:
            updated.append(row)
            continue
        note = row.get("note", "")
        updated.append(
            {
                **row,
                "mode": "excluded",
                "note": "excluded by --exclude" if not note else f"{note} | excluded by --exclude",
            }
        )
    return updated


def audit_task(reader: ParquetReader, row: dict[str, str]) -> dict:
    pairs = parse_pairs(row["pairs"])
    if row["mode"] == "self_suffix":
        columns = [column for pair in pairs for column in pair]
        source_df = target_df = reader.read_columns(row["target_repo"], row["target_config"], row["target_split"], columns)
    else:
        source_df = reader.read_columns(row["source_repo"], row["source_config"], row["source_split"], [pair[0] for pair in pairs])
        target_df = reader.read_columns(row["target_repo"], row["target_config"], row["target_split"], [pair[1] for pair in pairs])

    errors = 0
    warnings = 0
    issue_rows = 0
    checked_pairs = 0
    codes: Counter[str] = Counter()
    examples: list[dict] = []
    notes: list[str] = []

    if len(source_df) != len(target_df):
        errors += 1
        codes["row_count_mismatch"] += 1
        notes.append(f"row_count_mismatch: {len(source_df)} vs {len(target_df)}")

    limit = min(len(source_df), len(target_df))
    for row_idx in range(limit):
        row_issues = []
        row_suppressed = []
        row_has_issue = False
        for source_col, target_col in pairs:
            source_value = normalize_value(source_df.iloc[row_idx][source_col])
            target_value = normalize_value(target_df.iloc[row_idx][target_col])
            extracted_pairs, structural_errors = audit_text_pairs(source_value, target_value, row["lang"])
            for structural_error in structural_errors:
                row_has_issue = True
                errors += 1
                code = "list_length_mismatch" if "length mismatch" in structural_error else "field_type_mismatch"
                codes[code] += 1
                if len(examples) < 10:
                    examples.append(
                        {
                            "row_idx": row_idx,
                            "field": target_col,
                            "code": code,
                            "message": structural_error,
                        }
                    )
            for path, source_text, translated_text in extracted_pairs:
                checked_pairs += 1
                before = len(row_issues)
                check_text_pair(
                    issues=row_issues,
                    suppressed=row_suppressed,
                    split=row["target_split"],
                    row_idx=row_idx,
                    field=f"{target_col}{path}",
                    source_text=source_text,
                    translated_text=translated_text,
                    unchanged_min_letters=12,
                    allow_unchanged_title_like=allow_title_like(target_col),
                )
                if len(row_issues) > before:
                    row_has_issue = True
        for issue in row_issues:
            if issue.severity == "error":
                errors += 1
            elif issue.severity == "warning":
                warnings += 1
            codes[issue.code] += 1
            if len(examples) < 10:
                examples.append(
                    {
                        "row_idx": issue.row_idx,
                        "field": issue.field,
                        "code": issue.code,
                        "message": issue.message,
                        "source": issue.sample.get("source", ""),
                        "translation": issue.sample.get("translation", ""),
                    }
                )
        if row_has_issue:
            issue_rows += 1

    return {
        **row,
        "status": "ok",
        "checked_rows": limit,
        "rows_with_issues": issue_rows,
        "checked_pairs": checked_pairs,
        "errors": errors,
        "warnings": warnings,
        "top_codes": dict(codes.most_common(10)),
        "notes": notes,
        "examples": examples,
    }


def rebuild_summary(plan_rows: list[dict[str, str]], task_path: Path, output_dir: Path) -> None:
    task_rows = []
    active_task_keys = {task_key(row) for row in plan_rows if row["mode"] in AUDITABLE_MODES}
    if task_path.exists():
        with task_path.open(encoding="utf-8") as file:
            latest = {}
            for line in file:
                row = json.loads(line)
                key = task_key(row)
                if key in active_task_keys:
                    latest[key] = row
            task_rows = list(latest.values())

    summary: dict[tuple[str, str], dict] = {}
    for task in task_rows:
        key = (task["dataset"], task["lang"])
        item = summary.setdefault(
            key,
            {
                "dataset": task["dataset"],
                "language": task["lang"],
                "repo": task["target_repo"],
                "status": "checked",
                "checked_rows": 0,
                "checked_pairs": 0,
                "rows_with_potential_issues": 0,
                "errors": 0,
                "warnings": 0,
                "issue_codes": Counter(),
                "notes": [],
                "examples": [],
                "audited_tasks": 0,
            },
        )
        if task.get("status") != "ok":
            item["status"] = task.get("status") or "failed"
            item["notes"].append(task.get("error", "failed audit task"))
            continue
        item["checked_rows"] += int(task.get("checked_rows", 0))
        item["checked_pairs"] += int(task.get("checked_pairs", 0))
        item["rows_with_potential_issues"] += int(task.get("rows_with_issues", 0))
        item["errors"] += int(task.get("errors", 0))
        item["warnings"] += int(task.get("warnings", 0))
        item["audited_tasks"] += 1
        item["issue_codes"].update(task.get("top_codes", {}))
        item["notes"].extend(task.get("notes", []))
        item["examples"].extend(task.get("examples", [])[:2])

    for row in plan_rows:
        key = (row["dataset"], row["lang"])
        if key in summary:
            continue
        summary[key] = {
            "dataset": row["dataset"],
            "language": row["lang"],
            "repo": row["target_repo"],
            "status": row["mode"],
            "checked_rows": 0,
            "checked_pairs": 0,
            "rows_with_potential_issues": 0,
            "errors": 0,
            "warnings": 0,
            "issue_codes": Counter(),
            "notes": [row.get("note", "")],
            "examples": [],
            "audited_tasks": 0,
        }

    rows = []
    for item in sorted(summary.values(), key=lambda x: (x["dataset"], x["language"])):
        checked = int(item["checked_rows"])
        pct = (int(item["rows_with_potential_issues"]) / checked * 100) if checked else None
        status = item["status"]
        if status == "checked":
            if item["errors"]:
                status = "errors"
            elif item["warnings"]:
                status = "warnings"
            else:
                status = "ok"
        rows.append(
            {
                "dataset": item["dataset"],
                "language": item["language"],
                "repo": item["repo"],
                "status": status,
                "checked_rows": checked,
                "checked_pairs": item["checked_pairs"],
                "rows_with_potential_issues": item["rows_with_potential_issues"],
                "potential_issue_pct": "" if pct is None else round(pct, 4),
                "errors": item["errors"],
                "warnings": item["warnings"],
                "audited_tasks": item["audited_tasks"],
                "top_issue_codes": "; ".join(f"{code}:{count}" for code, count in item["issue_codes"].most_common(5)),
                "notes": " | ".join(note for note in item["notes"][:5] if note),
                "examples_json": json.dumps(item["examples"][:3], ensure_ascii=False),
            }
        )

    with (output_dir / "quality_summary.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    with (output_dir / "quality_summary.json").open("w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", default="conf/quality/hf_audit_plan.csv")
    parser.add_argument("--output-dir", default="reports/translation_coverage")
    parser.add_argument("--cache-dir", default=".cache/hf_parquet")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Skip DATASET:LANG pairs, for example --exclude FaithDial:fr. Can be repeated or comma-separated.",
    )
    parser.add_argument("--limit-tasks", type=int, default=0)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    task_path = output_dir / "quality_tasks.jsonl"
    if args.reset and task_path.exists():
        task_path.unlink()

    with Path(args.plan).open(encoding="utf-8") as file:
        plan_rows = list(csv.DictReader(file))
    plan_rows = apply_exclusions(plan_rows, parse_exclusions(args.exclude))
    work = [row for row in plan_rows if row["mode"] in AUDITABLE_MODES]
    completed = read_existing_tasks(task_path)
    reader = ParquetReader(Path(args.cache_dir))

    remaining = [row for row in work if task_key(row) not in completed]
    if args.limit_tasks:
        remaining = remaining[: args.limit_tasks]
    start = time.time()
    print(f"tasks total={len(work)} completed={len(completed)} remaining={len(remaining)}", flush=True)
    with task_path.open("a", encoding="utf-8") as file:
        for idx, row in enumerate(remaining, start=1):
            label = f"{row['dataset']} {row['lang']} {row['target_config']}/{row['target_split']}"
            try:
                result = audit_task(reader, row)
                print(
                    f"[{idx}/{len(remaining)}] {label}: rows={result['checked_rows']} "
                    f"issue_rows={result['rows_with_issues']} errors={result['errors']} warnings={result['warnings']}",
                    flush=True,
                )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                status = "missing_split" if "no parquet files" in str(exc) else "failed"
                result = {**row, "status": status, "error": error}
                print(f"[{idx}/{len(remaining)}] FAIL {label}: {result['error']}", flush=True)
            file.write(json.dumps(result, ensure_ascii=False) + "\n")
            file.flush()
    rebuild_summary(plan_rows, task_path, output_dir)
    print(f"done seconds={time.time() - start:.1f}", flush=True)


if __name__ == "__main__":
    main()
