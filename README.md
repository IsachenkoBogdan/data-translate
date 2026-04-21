# data-translate

`data-translate` is a local workflow package for translating dialogue datasets and preparing or running evaluation artifacts.

Current scope:
- translate dialogue datasets to French without changing task schema
- inspect and reformat external candidate translations
- run LLM-based evaluation and benchmark judging

Main package path:
- `src/data_translate`

CLI:

```bash
uv run data-translate translate --dataset faithdial
uv run data-translate evaluate --dataset faithdial
uv run data-translate reformat --dataset globalwoz --run ff
uv run data-translate inspect-source --dataset globalwoz --run ff
uv run data-translate benchmark-judge --run translation_judge
```

Config layout:
- `conf/datasets` dataset specs
- `conf/workflows` workflow defaults
- `conf/runs` run presets
- `conf/llm`, `conf/runtime`, `conf/prompts` runtime and judging settings

Code layout:
- `src/data_translate/config` typed config models and builders
- `src/data_translate/workflows` workflow entrypoints
- `src/data_translate/services` orchestration services
- `src/data_translate/domain` core translation/eval logic
- `src/data_translate/adapters` translation and LLM adapters
- `src/data_translate/engine` artifacts, reports, manifests, checkpoints
