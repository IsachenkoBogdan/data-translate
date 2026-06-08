# Extending

This page is for the three common extension tasks:

- add a new dataset
- add a Hub upload config
- add a new translation backend
- add a new judge adapter or provider

The project is already structured for these extension points. You do not need to invent a new integration pattern.

## Add a new dataset

### 1. Create `conf/datasets/<dataset>.yaml`

Start from the closest existing dataset.

Minimal HF-backed example:

```yaml
dataset_id: mydataset
source:
  hf_dataset_id: org/mydataset
  hf_revision: 0123456789abcdef
artifacts:
  translated_basename: org_mydataset
translation:
  source_lang: en
  target_lang: fr
  backend:
    provider: google
  rules:
    - source: text
      target: text_fr
      strategy: text
      cache: true
evaluation:
  source_lang: English
  target_lang: French
  domain: short description of what should stay invariant
  split: all
  seed: 42
  inputs:
    source:
      kind: source
    translation:
      kind: translated
  sampling:
    strategy: per_split_random
    dataset: source
    samples_per_split: 50
  field_pairs:
    - name: text_fr
      source_dataset: source
      source_field: text
      source_format: text
      translation_dataset: translation
      translation_field: text_fr
      translation_format: text
```

### 2. Choose the right translation strategy

Use:

- `text` for one scalar text field
- `text_list` for list of strings
- `dialog_turns_content` for list of turn objects
- `weblinx_query` for WebLINX-style action traces

If none matches, add a new strategy instead of abusing an existing one.

Strategy registry:
- [registry.py](../src/data_translate/domain/translation_strategies/registry.py)

### 3. Decide whether this is `translate` or `reformat`

Use `translate` when the project should translate the source itself.

Use `reformat` when:
- you already have an external candidate translation
- the candidate must be aligned back to the source schema
- the external data is not the source of truth

Reference example:
- [globalwoz.yaml](../conf/datasets/globalwoz.yaml)

### 4. Verify config before running

```bash
make config-show WORKFLOW=translate DATASET=mydataset
make config-show WORKFLOW=evaluate DATASET=mydataset
```

### 5. Run it

```bash
make translate DATASET=mydataset
make evaluate DATASET=mydataset
```

### 6. Add upload config when the dataset should go to Hugging Face

Create `conf/uploads/<upload_id>.yaml` after a translated artifact exists. Upload configs describe the parquet export layout used by the DeepPavlov Hugging Face org.

Use the closest existing upload config:

- `daily_dialog_fr.yaml` for one default config under `data/`
- `canard_fr.yaml` for retrieval datasets with `corpus`, `queries`, and `qrels`
- `clarqa_fr.yaml` for one repo with several dataset configs
- `statcan_dialog_fr.yaml` for serialized dialog content where `content_fr` must replace `content`

Dry-run export:

```bash
uv run data-translate upload-datasets --upload mydataset_fr --config-root conf
```

Only push after inspecting the generated parquet files:

```bash
uv run data-translate upload-datasets --upload mydataset_fr --config-root conf --push --yes
```

## Add a new translation strategy

Add a new strategy when the field shape or invariants are meaningfully different.

### 1. Implement strategy file

Put it under:
- `src/data_translate/domain/translation_strategies`

What a strategy needs:
- translator function with signature compatible with current strategies
- input validator

Reference files:
- [text.py](../src/data_translate/domain/translation_strategies/text.py)
- [dialog.py](../src/data_translate/domain/translation_strategies/dialog.py)
- [weblinx.py](../src/data_translate/domain/translation_strategies/weblinx.py)

### 2. Register it

Update:
- [registry.py](../src/data_translate/domain/translation_strategies/registry.py)

Both maps must be updated:
- `STRATEGIES`
- `INPUT_VALIDATORS`

### 3. Use it in dataset config

```yaml
rules:
  - source: my_field
    target: my_field_fr
    strategy: my_strategy
```

### 4. Add tests

Good tests usually cover:
- valid input shape
- invalid input shape
- invariant preservation
- multiline / escaping edge cases if the format is structured

## Add a new translation backend

This is the path for a new translator such as another HTTP provider.

### 1. Add backend config model

Edit:
- [models_dataset_translation.py](../src/data_translate/config/models_dataset_translation.py)

Pattern:

```python
class MyBackendModel(BaseModel):
    provider: Literal["mybackend"] = "mybackend"
    api_key_env: str = Field(min_length=1)
```

Then include it in `TranslationBackendModel`.

### 2. Implement adapter

Put it in:
- `src/data_translate/adapters`

It must satisfy the `TranslationAdapter` protocol:
- [translation_base.py](../src/data_translate/adapters/translation_base.py)

Required methods:
- `translate(text, use_cache=...) -> TranslationResult`
- `close()`

### 3. Wire it into factory

Edit:
- [translation_factory.py](../src/data_translate/adapters/translation_factory.py)

Add:
- import
- `isinstance(...)` branch
- correct language-code normalization if provider needs a special format

### 4. Add a run preset

Example:

```yaml
run_name: mybackend
translation:
  backend:
    provider: mybackend
    api_key_env: MYBACKEND_API_KEY
```

Location:
- `conf/runs/translate/mybackend.yaml`

### 5. Test it

At minimum:
- config validation
- adapter success path
- adapter error path
- factory construction

## Add a new judge provider or adapter

This is for evaluation-side LLMs, not for dataset translation.

### 1. Decide whether LiteLLM is enough

If the provider works through LiteLLM, the cheapest path is:
- add provider mapping if needed
- keep using [litellm_adapter.py](../src/data_translate/adapters/litellm_adapter.py)

If it needs custom behavior, create a new adapter implementing:
- [llm_base.py](../src/data_translate/adapters/llm_base.py)

### 2. Wire it in

Edit:
- [llm_factory.py](../src/data_translate/adapters/llm_factory.py)

Either:
- map new provider to the existing LiteLLM builder
- or add a new builder that returns your custom adapter

### 3. Add LLM config

Example:

```yaml
provider: myjudge
api_key_env: MYJUDGE_API_KEY
base_url: https://api.example.com/v1
model: my-model
temperature: 0.0
```

Put it in:
- `conf/llm/myjudge.yaml`

### 4. Add reusable evaluation run presets if useful

Example:

```yaml
run_name: myjudge_fast
llm:
  provider: myjudge
  api_key_env: MYJUDGE_API_KEY
  base_url: https://api.example.com/v1
  model: my-model
runtime:
  requests_per_minute: 30
```

Put it in:
- `conf/runs/evaluate/myjudge_fast.yaml`

## Build your own config cleanly

There are two sane ways to do this.

### Option 1. CLI overrides

Best for one experiment:

```bash
uv run data-translate evaluate \
  --dataset faithdial \
  --set llm.model=openai/gpt-5.4-mini \
  --set runtime.requests_per_minute=30
```

### Option 2. Run preset

Best for repeatable runs:

```yaml
run_name: my_eval
llm:
  model: openai/gpt-5.4-mini
runtime:
  requests_per_minute: 30
```

Save it under:
- `conf/runs/evaluate/my_eval.yaml`

Then run:

```bash
make evaluate DATASET=faithdial RUN=my_eval
```

## What not to change casually

Do not silently change:

- dataset schema
- split semantics
- role labels
- placeholders
- special tokens
- action syntax in structured formats like `WebLINX`

If the format is structured, preserve structure first and translate only the natural-language payloads inside it.
