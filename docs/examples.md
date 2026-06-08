# Examples

This page shows practical config patterns you can copy and adapt.

## 1. Simple scalar text dataset

Use this when each row has one plain text field.

Example source row:

```json
{
  "id": "42",
  "text": "Hello, how are you?"
}
```

Dataset config:

```yaml
dataset_id: my_text_dataset
source:
  hf_dataset_id: org/my_text_dataset
  hf_revision: 0123456789abcdef
artifacts:
  translated_basename: org_my_text_dataset
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
  domain: open-domain short text
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

Run:

```bash
make translate DATASET=my_text_dataset
make evaluate DATASET=my_text_dataset
```

## 2. List-of-utterances dataset

Use this when one field is a list of text items and order matters.

Example source row:

```json
{
  "dialogue_id": "abc",
  "history": [
    "Hi",
    "Can you help me book a flight?"
  ],
  "knowledge": "Flights are available on weekdays."
}
```

Dataset config:

```yaml
dataset_id: my_list_dataset
source:
  hf_dataset_id: org/my_list_dataset
artifacts:
  translated_basename: org_my_list_dataset
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
    - source: knowledge
      target: knowledge_fr
      strategy: text
      cache: true
evaluation:
  source_lang: English
  target_lang: French
  domain: knowledge-grounded dialogue
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
    - name: history_fr
      source_dataset: source
      source_field: history
      source_format: text_list
      translation_dataset: translation
      translation_field: history_fr
      translation_format: text_list
    - name: knowledge_fr
      source_dataset: source
      source_field: knowledge
      source_format: text
      translation_dataset: translation
      translation_field: knowledge_fr
      translation_format: text
```

This is the same pattern as `faithdial`.

## 3. Dialog turns dataset

Use this when the row contains a list of turn objects and only turn content should be translated.

Example source row:

```json
{
  "conversation_id": "1",
  "text": [
    {"role": "user", "content": "I need a flight from Boston to Denver."},
    {"role": "assistant", "content": "What date would you like to travel?"}
  ],
  "label": "book"
}
```

Dataset config:

```yaml
dataset_id: my_dialog_dataset
source:
  hf_dataset_id: org/my_dialog_dataset
artifacts:
  translated_basename: org_my_dialog_dataset
translation:
  source_lang: en
  target_lang: fr
  backend:
    provider: google
  rules:
    - source: text
      target: text
      strategy: dialog_turns_content
      cache: false
evaluation:
  source_lang: English
  target_lang: French
  domain: task-oriented dialogue
  split: all
  seed: 42
  inputs:
    source:
      kind: source
    translation:
      kind: translated
  sampling:
    strategy: stratified_by_field
    dataset: source
    field: label
    samples_per_value: 25
  field_pairs:
    - name: text
      source_dataset: source
      source_field: text
      source_format: dialog_turns
      translation_dataset: translation
      translation_field: text
      translation_format: dialog_turns
```

This is the same pattern as `airdialog`.

## 4. WebLINX-like structured query dataset

Use this when a single text field mixes natural language with action syntax and only the natural-language parts should be translated.

Example source row:

```text
User: Find the cheapest flight
Agent: say(speaker="navigator", utterance="Please wait")
Agent: click(x=120, y=44)
```

Dataset config:

```yaml
dataset_id: my_weblinx_like_dataset
source:
  hf_dataset_id: org/my_weblinx_like_dataset
artifacts:
  translated_basename: org_my_weblinx_like_dataset
translation:
  source_lang: en
  target_lang: fr
  backend:
    provider: google
  rules:
    - source: query
      target: query_fr
      strategy: weblinx_query
      cache: true
      options:
        translate_agent_say_utterance: true
evaluation:
  source_lang: English
  target_lang: French
  domain: web navigation query; action calls, URLs, code-like expressions, ids, xpaths, and DOM snippets should remain unchanged
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
    samples_per_split: 20
  field_pairs:
    - name: query_fr
      source_dataset: source
      source_field: query
      source_format: text
      translation_dataset: translation
      translation_field: query_fr
      translation_format: text
```

Use this only when the structure is close enough to current `weblinx_query` logic. If the action grammar is different, add a new strategy.

## 5. External candidate + reformat dataset

Use this when you already have a candidate translation file and need to align it back to source rows.

Source-of-truth:
- HF source dataset

Candidate:
- local external file under `data/external/...`

Dataset config:

```yaml
dataset_id: my_external_candidate
source:
  hf_dataset_id: org/my_source_dataset
artifacts:
  external_root: data/external/my_external_candidate
  translated_basename: my_external_candidates
  results_scope: my_external_candidate
reformat:
  missing_policy: skip_dialogues
  target_lang: fr
  candidates:
    vendor_a: vendor_a/output.json
  rules:
    source_dialogue_id_field: dialogue_id
    source_text_field: text
    source_history_field: history
    target_text_field: text
    target_history_field: history
    external_log_field: log
    external_turn_text_field: text
    turns_per_row: 2
    user_turn_offset: 0
    history_role_cycle:
      - user
      - assistant
    history_content_field: content
    history_role_field: role
    variant_field: reformat_variant
    backup_fields:
      text: source_text
      history: source_history
evaluation:
  source_lang: English
  target_lang: French
  domain: task-oriented dialogue
  split: all
  seed: 42
  inputs:
    translation:
      kind: path
      path: ""
  sampling:
    strategy: per_split_random
    dataset: translation
    samples_per_split: 50
  field_pairs:
    - name: text
      source_dataset: translation
      source_field: source_text
      source_format: text
      translation_dataset: translation
      translation_field: text
      translation_format: text
```

Run:

```bash
make inspect-source DATASET=my_external_candidate RUN=vendor_a
make reformat DATASET=my_external_candidate RUN=vendor_a
make evaluate DATASET=my_external_candidate RUN=vendor_a
```

This is the same pattern as `globalwoz`.

## 6. Custom translation backend run preset

Use a run preset when the dataset stays the same but translator changes.

Example `conf/runs/translate/deepl_fast.yaml`:

```yaml
run_name: deepl_fast
runtime:
  concurrency: 8
  max_retries: 5
  retry_sleep: 1.0
translation:
  backend:
    provider: deepl
    api_key_env: DEEPL_API_KEY
```

Run:

```bash
make translate DATASET=faithdial RUN=deepl_fast
```

## 7. Custom judge model run preset

Use a run preset when evaluation model and runtime should be reusable.

Example `conf/runs/evaluate/gpt54mini.yaml`:

```yaml
run_name: gpt54mini
llm:
  provider: openrouter
  api_key_env: OPENROUTER_API_KEY
  base_url: https://openrouter.ai/api/v1
  model: openai/gpt-5.4-mini
runtime:
  requests_per_minute: 30
  max_completion_tokens: 300
```

Run:

```bash
make evaluate DATASET=faithdial RUN=gpt54mini
```

## 8. One-off override instead of a preset

Use this when the change is experimental and not worth a new file.

```bash
uv run data-translate evaluate \
  --dataset weblinx \
  --set llm.model=openai/gpt-5.4-mini \
  --set runtime.requests_per_minute=30
```

## 9. Sanity-check before long runs

Always inspect the merged config before expensive runs:

```bash
make config-show WORKFLOW=translate DATASET=my_dialog_dataset
make config-show WORKFLOW=evaluate DATASET=my_dialog_dataset RUN=gpt54mini
```

If the merged config is wrong, fix config first. Do not debug a 5-hour run from guesswork.

## 10. Export and upload to Hugging Face

Use this after `translate` / `reformat` and `check-translation` have passed.

Example upload config for a dataset where `text_fr` should become the exported `text` column:

```yaml
upload_id: my_text_dataset_fr
dataset_id: my_text_dataset
language: fr
hub:
  repo_id: DeepPavlov/my_text_dataset_fr
  type: dataset
  visibility: public
  mode: create_or_update
source:
  path: data/translated/fr/org_my_text_dataset/default
export:
  local_dir: data/hf_exports/my_text_dataset_fr
  layout: single_config
  config_name: default
  data_dir: data
  splits:
    train: train
    validation: validation
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

Dry-run export:

```bash
uv run data-translate upload-datasets --upload my_text_dataset_fr --config-root conf
```

Push to Hugging Face:

```bash
hf auth whoami
uv run data-translate upload-datasets --upload my_text_dataset_fr --config-root conf --push --yes
```

For all configured uploads:

```bash
uv run data-translate upload-datasets --all --config-root conf
uv run data-translate upload-datasets --all --config-root conf --push --yes
```
