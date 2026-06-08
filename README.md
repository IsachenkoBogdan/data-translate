# data-translate

`data-translate` - локальный пакет для перевода диалоговых датасетов, проверки качества перевода, подготовки parquet-выгрузок для Hugging Face Hub и запуска оценочных экспериментов.

## Артефакт проектной практики

Этот репозиторий является одним из технических артефактов проектной практики по DialogMTEB. DialogMTEB - направление бенчмарков для оценки text embedding моделей на диалоговых задачах: классификации, retrieval, reranking, pair classification и semantic matching. Практическая цель работы - расширить бенчмарк за пределы английского языка, подготовив переведенные диалоговые датасеты с сохранением исходных схем, меток, разбиений и совместимости с оценкой.

Этот репозиторий закрывает французскую часть проекта: воспроизводимые конфиги перевода, переиспользуемые стратегии перевода, проверки качества, parquet export и автоматизацию загрузки в Hugging Face Hub. Сопутствующий репозиторий [interpparietes/DialogMTEB](https://github.com/interpparietes/DialogMTEB) закрывает notebook-based эксперименты и русскоязычную часть проекта.

Основные публичные артефакты:
- код и воспроизводимый pipeline: этот репозиторий
- загруженные французские датасеты: Hugging Face repos из таблицы статуса ниже
- презентация и видео-питч: отдельные артефакты для Talent Track

## Команда и распределение задач

Руководитель проекта: Леднева Дарья. Зона ответственности руководителя: постановка научной задачи, консультации по методологии DialogMTEB/MTEB, рецензирование результатов и контроль исследовательской логики.

| Участник | Степень участия | Зоны ответственности | Основные артефакты |
| --- | --- | --- | --- |
| Кремнева Полина | 50% | Русскоязычная часть проекта; перевод датасетов с английского на русский; notebook-based эксперименты; LLM-оценка качества перевода и промпты для проверки | [interpparietes/DialogMTEB](https://github.com/interpparietes/DialogMTEB), русские переводы и материалы оценки |
| Богдан Исаченко | 50% | Франкоязычная часть проекта; унифицированная инфраструктура перевода; CLI, конфиги датасетов, стратегии перевода, sanity checks, parquet export и загрузка в Hugging Face | этот репозиторий, `conf/datasets`, `conf/uploads`, `check-translation`, `upload-datasets`, французские HF-датасеты |

Для защиты рекомендуется отразить это же разделение в презентации отдельным слайдом: Полина показывает русскоязычный перевод и LLM-as-a-judge оценку, Богдан показывает французский pipeline, контроль качества, загрузку датасетов и воспроизводимость.

Текущий scope:
- перевод диалоговых датасетов на французский без изменения task schema
- инспекция и reformat внешних candidate translations
- экспорт переведенных артефактов в parquet layout, используемый Hugging Face org `DeepPavlov`
- запуск LLM-based оценки и benchmark judging

Основной пакет:
- `src/data_translate`

Документация:
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

Make-команды:

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

Общий формат Make-команд:

```bash
make translate DATASET=faithdial
make evaluate DATASET=weblinx
make reformat DATASET=globalwoz RUN=ff
make config-show WORKFLOW=translate DATASET=airdialog
make upload-datasets
```

Типовой workflow:

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

Примечания:
- датасеты загружаются с Hugging Face, если в конфиге задан `source.hf_dataset_id`
- `globalwoz` - основное исключение с внешним источником перевода; для него используется `reformat`, а не `translate`
- `check-translation` - sanity check перед загрузкой: схема, число строк, длины списков, пустые переводы, подозрительный непереведенный английский текст и сохранение WebLINX action sequence
- технические значения вроде URLs, имен файлов, attachments, путей, emails и hash-like ids игнорируются в unchanged warnings
- `upload-datasets` читает `conf/uploads/*.yaml`, экспортирует локальные переводы в parquet под `data/hf_exports` и загружает в Hugging Face только с `--push --yes`
- evaluation - отдельный workflow; он не запускается автоматически после перевода
- OpenRouter поддерживается для judge models через `conf/llm/translation_judge.yaml`

Статус датасетов:

| Исходный датасет | Локальный dataset id | French Hub repo | Статус |
| --- | --- | --- | --- |
| DailyDialog Manually Labelled Multi-turn Dialogue Dataset | `daily_dialog` | [DeepPavlov/daily_dialog_fr](https://huggingface.co/datasets/DeepPavlov/daily_dialog_fr) | Переведен и загружен |
| statcan-dialogue-dataset-retrieval | `statcan-dialogue-dataset-retrieval` | [DeepPavlov/statcan_dialog_fr](https://huggingface.co/datasets/DeepPavlov/statcan_dialog_fr) | Переведен и загружен |
| WebLINX | `weblinx` | [DeepPavlov/weblinx_fr](https://huggingface.co/datasets/DeepPavlov/weblinx_fr) | Переведен и загружен |
| FaithDial | `faithdial` | [DeepPavlov/faithdial_fr](https://huggingface.co/datasets/DeepPavlov/faithdial_fr) | Переведен и загружен; текущий artifact содержит `history_fr` и `knowledge_fr` |
| Multi2WOZ / MultiWOZ | `globalwoz` | [DeepPavlov/multiwoz_fr](https://huggingface.co/datasets/DeepPavlov/multiwoz_fr) | Переведен и загружен |
| air-dialogue | `airdialog` | [DeepPavlov/air_dialog_fr](https://huggingface.co/datasets/DeepPavlov/air_dialog_fr) | Переведен и загружен |
| CANARD | `canard_queries` | [DeepPavlov/canard_fr](https://huggingface.co/datasets/DeepPavlov/canard_fr) | Переведен и загружен |
| ClarQA | `clarqa_multi_turn`, `clarqa_single_turn` | [DeepPavlov/clarqa_fr](https://huggingface.co/datasets/DeepPavlov/clarqa_fr) | Переведен и загружен |
| MANtIS | `mantis` | Планируется | Перевод в процессе; будет загружен после завершения и проверок |
| Wizard of Wikipedia / WoW | `wizard_of_wikipedia` | Планируется | Перевод в процессе; будет загружен после завершения и проверок |
| Abg-CoQA | `coqa_abg` | Планируется | Перевод в процессе; config подготовлен, upload после завершения и проверок |
| Coral | `coral_*` | Планируется | Перевод в процессе; configs подготовлены, upload после завершения и проверок |

План дальнейших улучшений:
- добавить `mt-metrics-eval` как внешний calibration benchmark для оценки judge quality на стандартных MT human-eval данных
- оставить WMT-style benchmark judging, но валидировать его небольшим in-domain bilingual audit для качества перевода диалогов
- добавить опциональную LLM-проверку второго уровня для unchanged-translation warnings: дешевый checker собирает подозрительные кандидаты, а LLM решает, является ли текст осмысленным непереведенным английским, и возвращает структурированную French replacement
- сдвинуть judge prompting к rubric-based direct assessment для dialogue turns, используя dialogue history как контекст, а не оценивая весь диалог одним запросом
- репортить judge quality по language pair и quality band, а не только одной глобальной корреляцией
- рассматривать DSPy prompt optimization как отдельный поздний эксперимент после появления небольшого human-labeled in-domain dev set

Структура конфигов:
- `conf/datasets` dataset specs
- `conf/uploads` Hugging Face parquet export/upload specs
- `conf/workflows` workflow defaults
- `conf/runs` run presets
- `conf/llm`, `conf/runtime`, `conf/prompts` runtime и judging settings

Структура кода:
- `src/data_translate/config` typed config models и builders
- `src/data_translate/workflows` workflow entrypoints
- `src/data_translate/services` orchestration services
- `src/data_translate/domain` core translation/eval logic
- `src/data_translate/adapters` translation и LLM adapters
- `src/data_translate/engine` artifacts, reports, manifests, checkpoints
