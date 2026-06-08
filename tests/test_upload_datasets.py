from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from datasets import Dataset, DatasetDict, load_dataset

from data_translate.cli.main import main as cli_main
from data_translate.cli.parser import build_parser
from data_translate.services.upload_datasets import run_upload_datasets


def test_upload_datasets_exports_single_config(tmp_path: Path) -> None:
    source_path = tmp_path / "translated"
    DatasetDict(
        {
            "train": Dataset.from_dict(
                {
                    "id": ["1"],
                    "text": ["hello"],
                    "text_fr": ["bonjour"],
                    "meta": ["keep"],
                }
            )
        }
    ).save_to_disk(str(source_path))

    config_root = tmp_path / "conf"
    upload_dir = config_root / "uploads"
    upload_dir.mkdir(parents=True)
    export_dir = tmp_path / "export"
    (upload_dir / "sample_fr.yaml").write_text(
        f"""
upload_id: sample_fr
dataset_id: sample
language: fr
hub:
  repo_id: DeepPavlov/sample_fr
  type: dataset
  visibility: public
source:
  path: {source_path}
export:
  local_dir: {export_dir}
  layout: single_config
  config_name: default
  data_dir: data
  splits:
    train: train
  transforms:
    - name: replace_columns
      columns:
        text: text_fr
    - name: drop_columns
      columns:
        - text_fr
    - name: select_columns
      columns:
        - id
        - text
        - meta
""",
        encoding="utf-8",
    )

    payload = run_upload_datasets(config_root=str(config_root), upload_ids=["sample_fr"])

    assert payload["pushed"] is False
    assert payload["exports"][0]["repo_id"] == "DeepPavlov/sample_fr"
    exported = load_dataset(str(export_dir), data_files={"train": "data/train-*.parquet"})["train"]
    assert exported.column_names == ["id", "text", "meta"]
    assert exported[0]["text"] == "bonjour"
    assert (export_dir / "README.md").exists()


def test_upload_datasets_requires_yes_for_push(tmp_path: Path) -> None:
    config_root = tmp_path / "conf"
    (config_root / "uploads").mkdir(parents=True)
    with pytest.raises(ValueError, match="without --yes"):
        run_upload_datasets(config_root=str(config_root), all_uploads=True, push=True, yes=False)


def test_upload_datasets_parser_and_cli_entrypoint() -> None:
    args = build_parser().parse_args(["upload-datasets", "--upload", "daily_dialog_fr"])
    assert args.command == "upload-datasets"
    assert args.uploads == ["daily_dialog_fr"]

    with patch("data_translate.cli.main.build_parser") as parser_builder, patch(
        "data_translate.cli.main.run_upload_datasets",
        return_value={"exports": [], "pushed": False, "commands": []},
    ) as upload_mock:
        parser_builder.return_value.parse_args.return_value = SimpleNamespace(
            command="upload-datasets",
            config_root="conf",
            uploads=["daily_dialog_fr"],
            all=False,
            push=False,
            yes=False,
        )
        cli_main()
    upload_mock.assert_called_once()
