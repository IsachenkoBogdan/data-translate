# Upload configs

These configs describe how a local translated `datasets.DatasetDict`
artifact should be exported to Hugging Face Hub parquet layout before
running `hf upload`.

They are intentionally declarative. The `upload-datasets` CLI reads them,
exports parquet files locally by default, and uploads only when called with
`--push --yes`.

1. Load `source.path` or every entry in `sources[]` with `datasets.load_from_disk`.
2. Apply split mappings and column transforms.
3. Write parquet shards under `export.local_dir`.
4. Upload `export.local_dir` to `hub.repo_id` when push mode is enabled.

Supported transform names used here:

- `replace_columns`: set destination columns from translated source columns.
- `drop_columns`: remove helper/source columns from the exported dataset.
- `select_columns`: keep only the listed columns and order them.
- `serialized_dialog_content`: for JSON-serialized dialog lists, replace
  each turn content field from a translated content field and optionally
  drop the translated helper key.

Use `source` for single translated artifacts and `sources` when one Hub repo
is assembled from several local translated artifacts, for example ClarQAv1
`multi_turn` and `single_turn`.
