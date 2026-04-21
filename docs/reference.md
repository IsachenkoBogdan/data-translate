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

## Strategy validation

Each strategy has an input validator. Validation entrypoints are registered in:
- [registry.py](/home/bodunok_/workspace/DialogMTEB/src/data_translate/domain/translation_strategies/registry.py:1)

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
- [models_dataset_translation.py](/home/bodunok_/workspace/DialogMTEB/src/data_translate/config/models_dataset_translation.py:1)

Backend instantiation happens in:
- [translation_factory.py](/home/bodunok_/workspace/DialogMTEB/src/data_translate/adapters/translation_factory.py:1)

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
- [llm_base.py](/home/bodunok_/workspace/DialogMTEB/src/data_translate/adapters/llm_base.py:1)

Current LiteLLM-based implementation:
- [litellm_adapter.py](/home/bodunok_/workspace/DialogMTEB/src/data_translate/adapters/litellm_adapter.py:1)

Provider routing:
- [llm_factory.py](/home/bodunok_/workspace/DialogMTEB/src/data_translate/adapters/llm_factory.py:1)

## Workflow registry

Registered workflows:

- `translate`
- `evaluate`
- `benchmark-judge`
- `reformat`
- `inspect-source`

The registry lives in:
- [workflow_registry.py](/home/bodunok_/workspace/DialogMTEB/src/data_translate/workflow_registry.py:1)

Hydra composition entrypoint:
- [composition.py](/home/bodunok_/workspace/DialogMTEB/src/data_translate/config/composition.py:1)

## Practical rules when adding a dataset

1. Prefer `DeepPavlov` HF dataset if it exists.
2. Do not change schema, split semantics, roles, placeholders, or special tokens.
3. Choose the narrowest translation strategy that matches the field shape.
4. Keep evaluation field pairs aligned with translated output fields.
5. For external candidates, add `inspect-source` and `reformat` config instead of treating them as source truth.

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
