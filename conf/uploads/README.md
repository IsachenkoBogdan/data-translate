# Настройки загрузки

Эти файлы описывают, как локальный переведенный артефакт
`datasets.DatasetDict` экспортируется в parquet-структуру Hugging Face Hub
перед запуском `hf upload`.

Настройки намеренно декларативные. Команда `upload-datasets` читает YAML,
по умолчанию экспортирует parquet-файлы локально и загружает их только при
явном запуске с `--push --yes`.

1. Загружает `source.path` или все записи из `sources[]` через `datasets.load_from_disk`.
2. Применяет сопоставление разбиений и преобразования колонок.
3. Записывает parquet-файлы в `export.local_dir`.
4. Загружает `export.local_dir` в `hub.repo_id`, если включен режим публикации.

Используемые преобразования:

- `replace_columns`: заменить исходные колонки переведенными колонками.
- `drop_columns`: удалить вспомогательные или исходные колонки.
- `select_columns`: оставить только перечисленные колонки в заданном порядке.
- `serialized_dialog_content`: для JSON-сериализованных списков реплик заменить
  поле текста реплики переведенным полем и, при необходимости, удалить
  вспомогательное поле перевода.

Используйте `source` для одного переведенного артефакта и `sources`, когда один
репозиторий Hub собирается из нескольких локальных артефактов, например из
`multi_turn` и `single_turn` для ClarQAv1.

## Готовые команды для оставшихся наборов

WoW публикуется одним upload-конфигом `wizard_of_wikipedia_fr`, но перед ним
нужно перевести корпус, а затем запросы: итоговый артефакт запросов подтянет
переведенный корпус и исходные `qrels`.

```bash
make translate DATASET=wizard_of_wikipedia_corpus SET="runtime.concurrency=16"
make translate DATASET=wizard_of_wikipedia_queries SET="runtime.concurrency=16"
make check-translation DATASET=wizard_of_wikipedia_queries
make upload-datasets-push UPLOAD=wizard_of_wikipedia_fr
```

Coral публикуется upload-конфигом `coral_fr`; он собирает `corpus`, `qrels`,
`queries` и `rewritten_queries`, поэтому нужны оба артефакта запросов.

```bash
make translate DATASET=coral_corpus SET="runtime.concurrency=16"
make translate DATASET=coral_queries SET="runtime.concurrency=16"
make translate DATASET=coral_rewritten_queries SET="runtime.concurrency=16"
make check-translation DATASET=coral_queries
make check-translation DATASET=coral_rewritten_queries
make upload-datasets-push UPLOAD=coral_fr
```
