from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactStore:
    scope_id: str
    workflow: str
    run_name: str
    results_root: Path
    records_path: Path
    summary_path: Path
    checkpoint_dir: Path
    cache_dir: Path
    materialized_output_path: Path | None = None


RESULTS_BASE = Path("results")
TRANSLATED_BASE = Path("data/translated")


def build_materialized_output_path(
    *,
    translated_basename: str,
    target_lang: str,
    run_name: str = "",
) -> Path | None:
    if not translated_basename or not target_lang:
        return None
    path = TRANSLATED_BASE / target_lang / translated_basename
    if run_name:
        path = path / run_name
    return path


def build_artifact_store(
    *,
    workflow: str,
    scope_id: str,
    run_name: str,
    translated_basename: str = "",
    target_lang: str = "",
    cache_namespace: str = "cache",
    materialized_run_name: str = "",
) -> ArtifactStore:
    results_root = RESULTS_BASE / scope_id / workflow / run_name
    materialized_output_path = build_materialized_output_path(
        translated_basename=translated_basename,
        target_lang=target_lang,
        run_name=materialized_run_name,
    )
    return ArtifactStore(
        scope_id=scope_id,
        workflow=workflow,
        run_name=run_name,
        results_root=results_root,
        records_path=results_root / "records.jsonl",
        summary_path=results_root / "summary.json",
        checkpoint_dir=results_root / "checkpoint",
        cache_dir=results_root / "cache" / cache_namespace,
        materialized_output_path=materialized_output_path,
    )
