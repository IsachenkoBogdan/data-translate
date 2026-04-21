import json
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


MANIFEST_FILENAME = "data-translate-manifest.json"


def manifest_path(root: str | Path) -> Path:
    return Path(root) / MANIFEST_FILENAME


def build_manifest_payload(
    *,
    artifact_kind: str,
    workflow: str,
    dataset_id: str,
    run_name: str,
    output_path: str,
    target_lang: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "artifact_kind": artifact_kind,
        "workflow": workflow,
        "dataset_id": dataset_id,
        "run_name": run_name,
        "target_lang": target_lang,
        "output_path": output_path,
        "created_at_utc": datetime.now(UTC).isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


def write_manifest(root: str | Path, payload: dict[str, Any]) -> Path:
    path = manifest_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def read_manifest(root: str | Path) -> dict[str, Any] | None:
    path = manifest_path(root)
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must contain a JSON object: {path}")
    return dict(data)
