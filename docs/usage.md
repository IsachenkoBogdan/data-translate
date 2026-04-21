# Usage

This project has a small number of workflows. Most users only need these:

- `translate`: load a source dataset and write a translated dataset
- `evaluate`: score a translated dataset with an LLM judge
- `reformat`: convert an external candidate translation into project schema
- `inspect-source`: inspect source-to-external coverage before `reformat`
- `benchmark-judge`: run judge experiments that are not tied to one dataset

## Typical runs

FaithDial:

```bash
make translate DATASET=faithdial
make evaluate DATASET=faithdial
```

WebLINX:

```bash
make translate DATASET=weblinx SET="runtime.concurrency=8"
make evaluate DATASET=weblinx
```

AirDialog:

```bash
make translate DATASET=airdialog
make evaluate DATASET=airdialog
```

GlobalWoZ:

```bash
make inspect-source DATASET=globalwoz RUN=ff
make reformat DATASET=globalwoz RUN=ff
make evaluate DATASET=globalwoz RUN=ff
```

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
