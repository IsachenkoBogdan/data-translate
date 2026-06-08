# Reference

## Dataset config shape

Each dataset spec in `conf/datasets/<dataset>.yaml` is built from a few sections.

Minimal translation dataset:

```yaml
dataset_id: faithdial
source:
  hf_dataset_id: DeepPavlov/FaithDial-ru
artifacts:
  translated_basename: DeepPavlov_FaithDial
translation:
  source_lang: en
  target_lang: fr
  backend:
    provider: google
  rules:
    - source: history
      target: history_fr
      strategy: text_list
      cache: true
```

Important sections:

- `source`: where the source dataset comes from
- `artifacts`: naming and output roots
- `translation`: translation rules and backend
- `evaluation`: judge setup and field pairs
- `reformat`: external-candidate conversion rules for datasets like `globalwoz`

Two common source patterns:

HF-backed dataset:

```yaml
source:
  hf_dataset_id: DeepPavlov/FaithDial-ru
  hf_revision: ed49d9732196e96d5291e11cfa416083b8ff699e
```

External-candidate dataset:

```yaml
source:
  hf_dataset_id: DeepPavlov/MultiWOZ-2.1
artifacts:
  external_root: data/external/globalwoz
  translated_basename: globalwoz_candidates
reformat:
  candidates:
    FF: FF/F&F_fr.json
```

## Translation strategies

Strategies define how a field is interpreted before sending text to a translation backend.

### `text`

Use for one scalar string field.

Expected shape:
- string-like scalar

Example:

```yaml
- source: knowledge
  target: knowledge_fr
  strategy: text
```

### `text_list`

Use for a list of short text items. The system first tries a marked whole-list translation, then falls back to item-by-item translation if parsing fails.

Expected shape:
- list of scalar text-like items

Example:

```yaml
- source: history
  target: history_fr
  strategy: text_list
```

### `dialog_turns_content`

Use for a list of turn objects where only the `content` field should be translated and roles must stay intact.

Expected shape:
- list of mappings
- each mapping must contain `content`

Example:

```yaml
- source: text
  target: text
  strategy: dialog_turns_content
```

This is used by `airdialog`.

### `weblinx_query`

Use for WebLINX-style mixed records containing natural language plus action calls.

What it does:
- translates `User:` blocks
- can translate natural language inside `Agent: say(..., utterance="...")`
- preserves action syntax, line count, and action sequence
- leaves DOM-ish actions and code-like text untouched

Relevant option:

```yaml
options:
  translate_agent_say_utterance: true
```

This is used by `weblinx`.

### `nested_text_fields`

Use for nested dict/list values when only specific text paths should be translated.

Example:

```yaml
- source: turn
  target: turn_fr
  strategy: nested_text_fields
  options:
    paths:
      - question
      - answers[].answer
```

### `deep_map_texts`

Use when every textual value inside a nested cell should be translated while preserving the original nested shape.

Example:

```yaml
- source: history_turns
  target: history_turns
  strategy: deep_map_texts
  options:
    exclude_keys:
      - id
```

This is used by `coqa_abg`.

## Strategy validation

Each strategy has an input validator. Validation entrypoints are registered in:
- [registry.py](../src/data_translate/domain/translation_strategies/registry.py)

That means adding a strategy is always two steps:
- implement the translator function
- implement the input validator and register both names

## Translation backends

Configured under `translation.backend`.

### `google`

Good default for bulk translation.

Example:

```yaml
backend:
  provider: google
```

### `deepl`

HTTP backend with API key and optional formality.

Example:

```yaml
backend:
  provider: deepl
  api_key_env: DEEPL_API_KEY
```

### `yandex`

HTTP backend with API key and folder config.

Example:

```yaml
backend:
  provider: yandex
  api_key_env: YANDEX_API_KEY
  folder_id_env: YANDEX_FOLDER_ID
```

Backend model types are declared in:
- [models_dataset_translation.py](../src/data_translate/config/models_dataset_translation.py)

Backend instantiation happens in:
- [translation_factory.py](../src/data_translate/adapters/translation_factory.py)

## Judge LLM adapters

Configured under `conf/llm/*.yaml`.

Supported providers in code:
- `openrouter`
- `openai`

Both go through the LiteLLM-based adapter layer.

OpenRouter example:

```yaml
provider: openrouter
api_key_env: OPENROUTER_API_KEY
base_url: https://openrouter.ai/api/v1
model: openai/gpt-4o-mini
```

OpenAI example:

```yaml
provider: openai
api_key_env: OPENAI_API_KEY
model: gpt-4o-mini
```

LLM adapter interface:
- [llm_base.py](../src/data_translate/adapters/llm_base.py)

Current LiteLLM-based implementation:
- [litellm_adapter.py](../src/data_translate/adapters/litellm_adapter.py)

Provider routing:
- [llm_factory.py](../src/data_translate/adapters/llm_factory.py)

## Workflow registry

Registered workflows:

- `translate`
- `evaluate`
- `benchmark-judge`
- `reformat`
- `inspect-source`

Additional CLI-only commands:

- `check-translation`
- `upload-datasets`

The registry lives in:
- [workflow_registry.py](../src/data_translate/workflow_registry.py)

Hydra composition entrypoint:
- [composition.py](../src/data_translate/config/composition.py)

## Practical rules when adding a dataset

1. Prefer `DeepPavlov` HF dataset if it exists.
2. Do not change schema, split semantics, roles, placeholders, or special tokens.
3. Choose the narrowest translation strategy that matches the field shape.
4. Keep evaluation field pairs aligned with translated output fields.
5. For external candidates, add `inspect-source` and `reformat` config instead of treating them as source truth.

## Upload config shape

Upload configs live in `conf/uploads/<upload_id>.yaml`. They are not Hydra workflow configs; they are declarative specs consumed by:

```bash
uv run data-translate upload-datasets --upload <upload_id> --config-root conf
```

Minimal single-config upload:

```yaml
upload_id: my_dataset_fr
dataset_id: my_dataset
language: fr
hub:
  repo_id: DeepPavlov/my_dataset_fr
  type: dataset
  visibility: public
  mode: create_or_update
source:
  path: data/translated/fr/DeepPavlov_my_dataset/default
export:
  local_dir: data/hf_exports/my_dataset_fr
  layout: single_config
  config_name: default
  data_dir: data
  splits:
    train: train
    test: test
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
```

Supported transform names:

- `replace_columns`: copy translated helper columns into canonical exported columns
- `drop_columns`: remove helper/source columns
- `select_columns`: keep and order final exported columns
- `serialized_dialog_content`: replace JSON-serialized turn `content` from a translated helper key such as `content_fr`

Multi-config uploads use `export.layout: multi_config` and `export.configs`. They can read one local artifact with `source`, or several artifacts with `sources` and per-config `source_config`.

Examples:

- `conf/uploads/canard_fr.yaml`
- `conf/uploads/clarqa_fr.yaml`
- `conf/uploads/statcan_dialog_fr.yaml`

Safety behavior:

- without `--push`, `upload-datasets` only writes local parquet exports under `data/hf_exports`
- with `--push --yes`, it runs `hf repos create ... --exist-ok` and `hf upload ...`
- `--push` without `--yes` is rejected

## Custom config patterns

### Override from CLI

Good for one-off experiments:

```bash
uv run data-translate evaluate \
  --dataset weblinx \
  --set llm.model=openai/gpt-5.4-mini \
  --set runtime.requests_per_minute=30
```

### Reusable run preset

Good when the same setup will be reused:

```yaml
run_name: gpt54mini
llm:
  model: openai/gpt-5.4-mini
runtime:
  requests_per_minute: 30
```

Location:
- `conf/runs/evaluate/gpt54mini.yaml`

### Inspect the merged config

Always verify the final merged object before a long run:

```bash
make config-show WORKFLOW=evaluate DATASET=weblinx RUN=gpt54mini
```
