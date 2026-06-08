import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from datasets import Dataset, DatasetDict, load_from_disk


@dataclass(frozen=True)
class UploadSelection:
    upload_id: str
    path: Path
    config: dict[str, Any]


def _upload_config_dir(config_root: str) -> Path:
    return Path(config_root) / "uploads"


def _load_upload_config(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"upload config must be a mapping: {path}")
    return payload


def list_upload_configs(config_root: str = "conf") -> list[UploadSelection]:
    config_dir = _upload_config_dir(config_root)
    selections: list[UploadSelection] = []
    for path in sorted(config_dir.glob("*.yaml")):
        config = _load_upload_config(path)
        upload_id = str(config.get("upload_id") or path.stem)
        selections.append(UploadSelection(upload_id=upload_id, path=path, config=config))
    return selections


def select_upload_configs(
    *,
    config_root: str = "conf",
    upload_ids: list[str] | None = None,
    all_uploads: bool = False,
) -> list[UploadSelection]:
    configs = list_upload_configs(config_root)
    if all_uploads:
        return configs
    requested = set(upload_ids or [])
    if not requested:
        raise ValueError("upload-datasets requires --all or at least one --upload")
    by_id = {item.upload_id: item for item in configs}
    missing = sorted(requested - set(by_id))
    if missing:
        raise ValueError(f"unknown upload config(s): {', '.join(missing)}")
    return [by_id[upload_id] for upload_id in upload_ids or []]


def _load_dataset_dict(path: str) -> DatasetDict:
    dataset = load_from_disk(path)
    if isinstance(dataset, DatasetDict):
        return dataset
    if isinstance(dataset, Dataset):
        return DatasetDict({"train": dataset})
    raise TypeError(f"expected Dataset or DatasetDict at {path}")


def _source_datasets(config: dict[str, Any]) -> dict[str, DatasetDict]:
    if "sources" in config:
        return {
            str(source["config_name"]): _load_dataset_dict(str(source["path"]))
            for source in config["sources"]
        }
    source = config.get("source")
    if not source:
        raise ValueError(f"{config.get('upload_id')}: upload config must define source or sources")
    return {"default": _load_dataset_dict(str(source["path"]))}


def _replace_columns(dataset: Dataset, columns: dict[str, str]) -> Dataset:
    def mapper(batch: dict[str, list[Any]]) -> dict[str, list[Any]]:
        return {target: batch[source] for target, source in columns.items()}

    return dataset.map(mapper, batched=True)


def _serialized_dialog_content(
    dataset: Dataset,
    *,
    column: str,
    translated_column: str,
    content_field: str,
    translated_content_field: str,
    drop_translated_content_field: bool,
) -> Dataset:
    def mapper(batch: dict[str, list[Any]]) -> dict[str, list[str]]:
        values: list[str] = []
        for source_value, translated_value in zip(batch[column], batch[translated_column], strict=True):
            source_turns = json.loads(source_value or "[]")
            translated_turns = json.loads(translated_value or "[]")
            if not isinstance(source_turns, list) or not isinstance(translated_turns, list):
                raise ValueError(f"{column} and {translated_column} must decode to lists")
            output_turns: list[dict[str, Any]] = []
            for source_turn, translated_turn in zip(source_turns, translated_turns, strict=False):
                if not isinstance(source_turn, dict) or not isinstance(translated_turn, dict):
                    output_turns.append(source_turn)
                    continue
                output_turn = dict(source_turn)
                if translated_content_field in translated_turn:
                    output_turn[content_field] = translated_turn[translated_content_field]
                if not drop_translated_content_field and translated_content_field in translated_turn:
                    output_turn[translated_content_field] = translated_turn[translated_content_field]
                output_turns.append(output_turn)
            values.append(json.dumps(output_turns, ensure_ascii=False))
        return {column: values}

    return dataset.map(mapper, batched=True)


def _apply_transforms(dataset: Dataset, transforms: list[dict[str, Any]]) -> Dataset:
    result = dataset
    for transform in transforms:
        name = transform["name"]
        if name == "replace_columns":
            result = _replace_columns(result, dict(transform.get("columns") or {}))
        elif name == "drop_columns":
            columns = [column for column in transform.get("columns", []) if column in result.column_names]
            if columns:
                result = result.remove_columns(columns)
        elif name == "select_columns":
            result = result.select_columns(list(transform.get("columns") or []))
        elif name == "serialized_dialog_content":
            result = _serialized_dialog_content(
                result,
                column=str(transform["column"]),
                translated_column=str(transform["translated_column"]),
                content_field=str(transform.get("content_field", "content")),
                translated_content_field=str(transform.get("translated_content_field", "content_fr")),
                drop_translated_content_field=bool(transform.get("drop_translated_content_field", True)),
            )
        else:
            raise ValueError(f"unknown upload transform: {name}")
    return result


def _config_entries(export: dict[str, Any]) -> list[dict[str, Any]]:
    if export["layout"] == "single_config":
        return [
            {
                "config_name": export.get("config_name", "default"),
                "data_dir": export.get("data_dir", "data"),
                "splits": export["splits"],
            }
        ]
    return [
        {
            "config_name": config["config_name"],
            "data_dir": config["data_dir"],
            "splits": config["splits"],
        }
        for config in export["configs"]
    ]


def _readme_text(config: dict[str, Any]) -> str:
    configs = []
    for entry in _config_entries(config["export"]):
        configs.append(
            {
                "config_name": entry["config_name"],
                "data_files": [
                    {
                        "split": output_split,
                        "path": f"{entry['data_dir']}/{output_split}-*",
                    }
                    for output_split in entry["splits"].values()
                ],
            }
        )
    front_matter = yaml.safe_dump({"configs": configs}, sort_keys=False, allow_unicode=True)
    repo_id = config["hub"]["repo_id"]
    return f"---\n{front_matter}---\n\n# {repo_id}\n\nFrench translated dataset exported by `data-translate upload-datasets`.\n"


def _write_split(dataset: Dataset, output_path: Path) -> int:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_parquet(str(output_path))
    return len(dataset)


def export_upload_config(selection: UploadSelection) -> dict[str, Any]:
    config = selection.config
    export = config["export"]
    export_dir = Path(export["local_dir"])
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True, exist_ok=True)

    sources = _source_datasets(config)
    written: list[dict[str, Any]] = []

    if export["layout"] == "single_config":
        source_dataset = sources["default"]
        data_dir = str(export.get("data_dir", "data"))
        transforms = list(export.get("transforms", []))
        for source_split, output_split in export["splits"].items():
            dataset = _apply_transforms(source_dataset[source_split], transforms)
            path = export_dir / data_dir / f"{output_split}-00000-of-00001.parquet"
            written.append({"split": output_split, "path": str(path), "rows": _write_split(dataset, path)})
    elif export["layout"] == "multi_config":
        for config_entry in export["configs"]:
            source_name = str(config_entry.get("source_config") or "default")
            source_dataset = sources[source_name]
            data_dir = str(config_entry["data_dir"])
            transforms = list(config_entry.get("transforms", []))
            for source_split, output_split in config_entry["splits"].items():
                dataset = _apply_transforms(source_dataset[source_split], transforms)
                path = export_dir / data_dir / f"{output_split}-00000-of-00001.parquet"
                written.append(
                    {
                        "config": config_entry["config_name"],
                        "split": output_split,
                        "path": str(path),
                        "rows": _write_split(dataset, path),
                    }
                )
    else:
        raise ValueError(f"unknown upload layout: {export['layout']}")

    (export_dir / "README.md").write_text(_readme_text(config), encoding="utf-8")
    return {
        "upload_id": selection.upload_id,
        "repo_id": config["hub"]["repo_id"],
        "export_dir": str(export_dir),
        "written": written,
    }


def _run_hf_command(args: list[str]) -> None:
    subprocess.run(args, check=True)


def push_upload(export_result: dict[str, Any], *, private: bool = False) -> list[list[str]]:
    repo_id = str(export_result["repo_id"])
    export_dir = str(export_result["export_dir"])
    create_cmd = ["hf", "repos", "create", repo_id, "--type", "dataset", "--exist-ok"]
    if private:
        create_cmd.append("--private")
    upload_cmd = [
        "hf",
        "upload",
        repo_id,
        export_dir,
        ".",
        "--type",
        "dataset",
        "--commit-message",
        f"Upload {repo_id.split('/')[-1]}",
    ]
    _run_hf_command(create_cmd)
    _run_hf_command(upload_cmd)
    return [create_cmd, upload_cmd]


def run_upload_datasets(
    *,
    config_root: str = "conf",
    upload_ids: list[str] | None = None,
    all_uploads: bool = False,
    push: bool = False,
    yes: bool = False,
) -> dict[str, Any]:
    if push and not yes:
        raise ValueError("refusing to upload without --yes")
    selections = select_upload_configs(config_root=config_root, upload_ids=upload_ids, all_uploads=all_uploads)
    exports = [export_upload_config(selection) for selection in selections]
    commands: list[list[list[str]]] = []
    if push:
        for selection, export_result in zip(selections, exports, strict=True):
            private = str(selection.config.get("hub", {}).get("visibility", "public")) == "private"
            commands.append(push_upload(export_result, private=private))
    return {"exports": exports, "pushed": push, "commands": commands}


def format_upload_summary(payload: dict[str, Any]) -> str:
    lines = ["upload-datasets:"]
    for export in payload["exports"]:
        row_count = sum(item["rows"] for item in export["written"])
        lines.append(f"- {export['upload_id']} -> {export['repo_id']}: {row_count} rows, {export['export_dir']}")
    if not payload["pushed"]:
        lines.append("dry-run: pass --push --yes to upload these exports to Hugging Face Hub")
    return "\n".join(lines)
