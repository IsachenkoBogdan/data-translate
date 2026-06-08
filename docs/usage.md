# Usage

This project has a small number of workflows. Most users only need these:

- `translate`: load a source dataset and write a translated dataset
- `evaluate`: score a translated dataset with an LLM judge
- `check-translation`: run simple pre-upload sanity checks on translated artifacts
- `reformat`: convert an external candidate translation into project schema
- `inspect-source`: inspect source-to-external coverage before `reformat`
- `upload-datasets`: export translated artifacts to Hugging Face parquet layout and optionally upload them
- `benchmark-judge`: run judge experiments that are not tied to one dataset

## Typical runs

FaithDial:

```bash
make translate DATASET=faithdial
make check-translation DATASET=faithdial
make evaluate DATASET=faithdial
```

WebLINX:

```bash
make translate DATASET=weblinx SET="runtime.concurrency=8"
make check-translation DATASET=weblinx
make evaluate DATASET=weblinx
```

AirDialog:

```bash
make translate DATASET=airdialog
make check-translation DATASET=airdialog MAX_ROWS_PER_SPLIT=1000
make evaluate DATASET=airdialog
```

GlobalWoZ:

```bash
make inspect-source DATASET=globalwoz RUN=ff
make reformat DATASET=globalwoz RUN=ff
make check-translation DATASET=globalwoz RUN=ff MAX_ROWS_PER_SPLIT=1000
make evaluate DATASET=globalwoz RUN=ff
```

Prepare Hub parquet export:

```bash
make upload-datasets UPLOAD=daily_dialog_fr
make upload-datasets
```

## Translation Sanity Checks

Run `check-translation` after translation or reformatting and before uploading a dataset:

```bash
make check-translation DATASET=faithdial
make check-translation DATASET=weblinx
make check-translation DATASET=globalwoz RUN=ff
```

For large datasets, use a row limit for a quick smoke check:

```bash
make check-translation DATASET=airdialog MAX_ROWS_PER_SPLIT=1000
```

The checker validates:

- source and translated split/row counts
- required translated columns from dataset config
- list and dialogue turn lengths
- empty translations for non-empty source text
- unchanged English-looking text in French fields
- WebLINX action sequence preservation

It intentionally suppresses unchanged-value warnings for technical strings that should remain stable: URLs, file names, attachments, paths, emails, and hash-like ids.

It writes summaries to `results/<dataset>/check-translation/<run>/summary.json` and exits with code `1` when it finds errors. Warnings, such as suspicious unchanged text, are reported but do not fail the command.

## Hugging Face Upload Exports

The local translated artifacts under `data/translated/...` are `datasets.save_to_disk` Arrow directories. Do not upload those directories directly to Hugging Face. The DeepPavlov org uses parquet files and, for some datasets, multiple configs represented by subdirectories such as `corpus/`, `queries/`, and `qrels/`.

Upload specs live in `conf/uploads/*.yaml`. They describe:

- one local translated artifact path via `source`, or several paths via `sources`
- target Hub repo id
- exported parquet layout
- split mapping
- column transforms, such as `dialog <- dialog_fr`
- validation expectations

Dry-run export for one dataset:

```bash
uv run data-translate upload-datasets --upload daily_dialog_fr --config-root conf
```

Dry-run export for all configured uploads:

```bash
uv run data-translate upload-datasets --all --config-root conf
```

The command writes exports under `data/hf_exports/<upload_id>` and prints a summary. It does not touch Hugging Face unless `--push --yes` is passed.

Upload one dataset:

```bash
uv run data-translate upload-datasets --upload daily_dialog_fr --config-root conf --push --yes
```

Upload all configured datasets:

```bash
uv run data-translate upload-datasets --all --config-root conf --push --yes
```

Before pushing, verify authentication:

```bash
hf auth whoami
```

Current upload configs:

- `daily_dialog_fr`: updates `DeepPavlov/daily_dialog_fr`; replaces the currently misaligned Hub parquet files with the cleaned local translation
- `air_dialog_fr`: creates/updates `DeepPavlov/air_dialog_fr`
- `canard_fr`: creates/updates `DeepPavlov/canard_fr` with `corpus`, `queries`, and `qrels`
- `clarqa_fr`: creates/updates `DeepPavlov/clarqa_fr` with `multi_turn` and `single_turn`
- `multiwoz_fr`: creates/updates `DeepPavlov/multiwoz_fr`
- `statcan_dialog_fr`: creates/updates `DeepPavlov/statcan_dialog_fr` with `queries` and `corpus`
- `weblinx_fr`: creates/updates `DeepPavlov/weblinx_fr`
- `faithdial_fr`: creates/updates `DeepPavlov/faithdial_fr`, but note that the current local artifact only includes `history_fr` and `knowledge_fr`

## How config is resolved

Runtime config is composed from:

1. `conf/workflows/<workflow>.yaml`
2. `conf/datasets/<dataset>.yaml`
3. `conf/runs/<workflow>/<run>.yaml` if `--run` is set
4. `--set key=value` overrides from CLI

To inspect the final merged config:

```bash
make config-show WORKFLOW=translate DATASET=weblinx
make config-show WORKFLOW=evaluate DATASET=faithdial
```

Two practical ways to customize behavior:

1. One-off override with `--set`

```bash
uv run data-translate translate \
  --dataset weblinx \
  --set runtime.concurrency=8 \
  --set translation.backend.provider=deepl \
  --set translation.backend.api_key_env=DEEPL_API_KEY
```

2. Reusable run preset in `conf/runs/<workflow>/<run>.yaml`

Example:

```yaml
run_name: deepl_fast
runtime:
  concurrency: 8
translation:
  backend:
    provider: deepl
    api_key_env: DEEPL_API_KEY
```

Run it with:

```bash
make translate DATASET=faithdial RUN=deepl_fast
```

## What gets downloaded and what stays local

- `airdialog`, `faithdial`, `weblinx`: source dataset is loaded from Hugging Face
- `globalwoz`: source is HF `MultiWOZ-2.1`, but candidate translation comes from `data/external/globalwoz`
- translated outputs are materialized under `data/translated/...`
- upload exports are materialized under `data/hf_exports/...`
- workflow artifacts and checkpoints go under `results/...`

## Evaluation

Evaluation is separate from translation. It does not auto-run after `translate`.

Typical sequence:

```bash
make translate DATASET=faithdial
make evaluate DATASET=faithdial
```

Judge LLM config comes from:

- `conf/llm/translation_judge.yaml` for OpenRouter
- `conf/llm/translation_judge_openai.yaml` for direct OpenAI API
- `conf/prompts/...` for judge prompts

Example with a different model through OpenRouter:

```bash
uv run data-translate evaluate \
  --dataset faithdial \
  --set llm.model=openai/gpt-4o-mini
```

Example with a reusable evaluation preset:

```yaml
run_name: gpt54mini
llm:
  provider: openrouter
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1
  model: openai/gpt-5.4-mini
runtime:
  requests_per_minute: 30
```

Save as `conf/runs/evaluate/gpt54mini.yaml`, then run:

```bash
make evaluate DATASET=faithdial RUN=gpt54mini
```

## Failure and resume behavior

- translation writes per-split checkpoints to `results/<dataset>/translate/<run>/checkpoint`
- rerunning the same command resumes from checkpoint
- evaluation writes records and summary under `results/<dataset>/evaluate/<run>`
- `config-show` is the first thing to run when behavior is unclear

## Where to look when adding something new

- new dataset config: `conf/datasets/<dataset>.yaml`
- new reusable run preset: `conf/runs/<workflow>/<run>.yaml`
- translation strategies: `src/data_translate/domain/translation_strategies`
- translation backends: `src/data_translate/adapters` and `src/data_translate/adapters/translation_factory.py`
- judge adapters: `src/data_translate/adapters/llm_factory.py`
- workflow registration: `src/data_translate/workflow_registry.py`
