# data-translate

`data-translate` is a local workflow package for translating dialogue datasets, checking translation quality, exporting Hub-ready parquet layouts, and running evaluation artifacts.

Current scope:
- translate dialogue datasets to French without changing task schema
- inspect and reformat external candidate translations
- export translated artifacts to the parquet layout used by the DeepPavlov Hugging Face org
- run LLM-based evaluation and benchmark judging

Main package path:
- `src/data_translate`

Docs:
- [docs/usage.md](docs/usage.md)
- [docs/reference.md](docs/reference.md)
- [docs/extending.md](docs/extending.md)
- [docs/examples.md](docs/examples.md)

CLI:

```bash
uv run data-translate translate --dataset faithdial
uv run data-translate evaluate --dataset faithdial
uv run data-translate reformat --dataset globalwoz --run ff
uv run data-translate inspect-source --dataset globalwoz --run ff
uv run data-translate check-translation --dataset faithdial
uv run data-translate upload-datasets --upload daily_dialog_fr
uv run data-translate benchmark-judge --run translation_judge
```

Make shortcuts:

```bash
make test
make translate DATASET=faithdial
make evaluate DATASET=weblinx
make reformat DATASET=globalwoz RUN=ff
make inspect-source DATASET=globalwoz RUN=ff
make check-translation DATASET=faithdial
make upload-datasets UPLOAD=daily_dialog_fr
make benchmark-judge RUN=translation_judge
```

Generic make form:

```bash
make translate DATASET=faithdial
make evaluate DATASET=weblinx
make reformat DATASET=globalwoz RUN=ff
make config-show WORKFLOW=translate DATASET=airdialog
make upload-datasets
```

Common flow:

```bash
make translate DATASET=faithdial
make check-translation DATASET=faithdial
make evaluate DATASET=faithdial

make translate DATASET=weblinx
make check-translation DATASET=weblinx
make evaluate DATASET=weblinx

make reformat DATASET=globalwoz RUN=ff
make check-translation DATASET=globalwoz RUN=ff
make evaluate DATASET=globalwoz RUN=ff

make upload-datasets UPLOAD=daily_dialog_fr
make upload-datasets-push UPLOAD=daily_dialog_fr
```

Notes:
- datasets are loaded from Hugging Face when configured with `source.hf_dataset_id`
- `globalwoz` is the main external-source exception and uses `reformat` instead of `translate`
- `check-translation` is a pre-upload sanity workflow for schema, row counts, list lengths, empty translations, unchanged English-like text, and WebLINX action preservation
- unchanged technical values such as URLs, file names, attachments, paths, emails, and hash-like ids are ignored by `check-translation`
- `upload-datasets` reads `conf/uploads/*.yaml`, exports local translated artifacts to parquet under `data/hf_exports`, and only pushes to Hugging Face when called with `--push --yes`
- evaluation is a separate workflow; it does not run automatically after translation
- OpenRouter is supported for judge models via `conf/llm/translation_judge.yaml`

Dataset status:

- translated and prepared for French upload: `daily_dialog`, `statcan-dialogue-dataset-retrieval`, `weblinx`, `airdialog`, `canard`, `clarqa`, `globalwoz` / MultiWOZ
- translated locally but not a full Hub-equivalent yet: `faithdial` currently has `history_fr` and `knowledge_fr`; the Spanish Hub analogue also translates response and label fields
- still unfinished: `mantis`, `wizard_of_wikipedia`, `coqa_abg`, `coral`

Next improvements:
- add `mt-metrics-eval` as an external calibration benchmark for judge quality on standard MT human-eval data
- keep WMT-style benchmark judging, but validate it with a small in-domain bilingual audit for dialogue translation quality
- add optional second-stage LLM verification for unchanged-translation warnings: the cheap checker should only collect suspicious candidates, while the LLM decides whether the text is meaningful untranslated English and returns a structured suggested French replacement
- move judge prompting further toward rubric-based direct assessment for dialogue turns, with dialogue history used as supporting context rather than scoring whole dialogues in one pass
- report judge quality per language pair and per quality band, not only as one global correlation
- treat DSPy prompt optimization as a later experiment, after a small human-labeled in-domain dev set exists

Config layout:
- `conf/datasets` dataset specs
- `conf/uploads` Hugging Face parquet export/upload specs
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
