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

## FaithDial

`faithdial_fr` публикуется полным набором `train/dev/test`, как
`DeepPavlov/faithdial_es`. Источник для перевода - `DeepPavlov/faithdial_es`:
он содержит исходные английские поля и уже нормализованную схему разбиений.
Текущий upload-конфиг выгружает поля `history_fr` и `knowledge_fr`; остальные
исходные поля сохраняются для совместимости.

```bash
make translate DATASET=faithdial SET="runtime.concurrency=16"
make check-translation DATASET=faithdial
make upload-datasets-push UPLOAD=faithdial_fr
```

## MultiWOZ

`multiwoz_fr` исторически был собран из внешнего кандидата GlobalWOZ через
`globalwoz` и `reformat`. Полный аудит против `DeepPavlov/MultiWOZ-2.1`
показал, что кандидат не является строгим построчным переводом: в нем меняются
значения слотов, времена, сущности и иногда сами реплики.

Для исправления используется прямой путь `multiwoz_direct`: он переводит только
`text` и `history[].content` из исходного `DeepPavlov/MultiWOZ-2.1`, а все
служебные поля и слоты оставляет без изменений.

```bash
make translate DATASET=multiwoz_direct SET="runtime.concurrency=16"
make check-translation DATASET=multiwoz_direct
make upload-datasets-push UPLOAD=multiwoz_fr_direct
```

После загрузки `multiwoz_fr_direct` репозиторий `DeepPavlov/multiwoz_fr`
содержит прямой перевод, а `conf/quality/multiwoz_fr.yaml` проверяет именно эту
схему.

## Команды воспроизводимости для WoW и Coral

WoW публикуется одним upload-конфигом `wizard_of_wikipedia_fr`. Для полной
воспроизводимости сначала переводится корпус, затем запросы: итоговый артефакт
запросов подтягивает переведенный корпус и исходные `qrels`.

```bash
make translate DATASET=wizard_of_wikipedia_corpus SET="runtime.concurrency=16"
make translate DATASET=wizard_of_wikipedia_queries SET="runtime.concurrency=16"
make check-translation DATASET=wizard_of_wikipedia_queries
make upload-datasets-push UPLOAD=wizard_of_wikipedia_fr
```

Coral публикуется upload-конфигом `coral_fr`; он собирает `corpus`, `qrels`
и `queries`, как уже опубликованные версии `DeepPavlov/coral_ru` и
`DeepPavlov/coral_es`. Команды ниже воспроизводят перевод и загрузку; после
публикации `DeepPavlov/coral_fr` проверяется quality-конфигами
`coral_fr_corpus` и `coral_fr_queries`.

```bash
make translate DATASET=coral_corpus SET="runtime.concurrency=16"
make translate DATASET=coral_queries SET="runtime.concurrency=16"
make check-translation DATASET=coral_queries
make upload-datasets-push UPLOAD=coral_fr
make check-translation QUALITY=coral_fr_corpus
make check-translation QUALITY=coral_fr_queries
```
