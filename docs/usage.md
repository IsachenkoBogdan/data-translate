# Использование

В проекте есть несколько основных сценариев. В большинстве случаев достаточно этих команд:

- `translate`: загрузить исходный набор данных и записать перевод;
- `evaluate`: оценить перевод с помощью языковой модели;
- `check-translation`: выполнить проверки перед загрузкой;
- `reformat`: привести внешний готовый перевод к схеме проекта;
- `inspect-source`: проверить покрытие исходных данных перед `reformat`;
- `upload-datasets`: экспортировать переводы в parquet и при необходимости загрузить их в Hugging Face;
- `benchmark-judge`: запустить отдельные эксперименты для моделей-оценщиков.

## Типовые запуски

FaithDial:

```bash
make translate DATASET=faithdial
make check-translation DATASET=faithdial
make evaluate DATASET=faithdial
```

WebLINX:

```bash
make translate DATASET=weblinx SET="runtime.concurrency=8"
make check-translation DATASET=weblinx
make evaluate DATASET=weblinx
```

AirDialog:

```bash
make translate DATASET=airdialog
make check-translation DATASET=airdialog MAX_ROWS_PER_SPLIT=1000
make evaluate DATASET=airdialog
```

GlobalWoZ:

```bash
make inspect-source DATASET=globalwoz RUN=ff
make reformat DATASET=globalwoz RUN=ff
make check-translation DATASET=globalwoz RUN=ff MAX_ROWS_PER_SPLIT=1000
make evaluate DATASET=globalwoz RUN=ff
```

Подготовка parquet-выгрузки для Hugging Face:

```bash
make upload-datasets UPLOAD=daily_dialog_fr
make upload-datasets
```

## Проверка перевода

`check-translation` нужно запускать после перевода или `reformat` и до загрузки набора данных:

```bash
make check-translation DATASET=faithdial
make check-translation DATASET=weblinx
make check-translation DATASET=globalwoz RUN=ff
```

Для больших наборов данных можно сначала выполнить быструю проверку на ограниченном числе строк:

```bash
make check-translation DATASET=airdialog MAX_ROWS_PER_SPLIT=1000
```

Проверка смотрит:

- совпадение разбиений и числа строк в исходном и переведенном варианте;
- наличие обязательных переведенных колонок из настроек набора данных;
- длины списков и диалоговых ходов;
- пустые переводы при непустом исходном тексте;
- подозрительно неизмененный английский текст во французских полях;
- сохранение последовательностей действий WebLINX.

Технические строки, которые должны оставаться стабильными, не считаются ошибками: ссылки, имена файлов, вложения, пути, почтовые адреса и похожие на хеши идентификаторы.

Отчет сохраняется в `results/<dataset>/check-translation/<run>/summary.json`. Команда завершится с кодом `1`, если найдены ошибки. Предупреждения, например подозрительно неизмененный текст, показываются в отчете, но сами по себе не ломают запуск.

## Загрузка в Hugging Face

Локальные переводы в `data/translated/...` сохранены как Arrow-директории `datasets.save_to_disk`. Их не нужно загружать в Hugging Face напрямую. Организация DeepPavlov использует parquet-файлы, а для некоторых наборов данных еще и несколько поднаборов вроде `corpus/`, `queries/` и `qrels/`.

Правила загрузки лежат в `conf/uploads/*.yaml`. Они описывают:

- один путь к локальному переводу через `source` или несколько путей через `sources`;
- целевой репозиторий Hugging Face;
- структуру parquet-выгрузки;
- сопоставление разбиений;
- преобразования колонок, например `dialog <- dialog_fr`;
- ожидаемые проверки перед публикацией.

Пробный экспорт одного набора данных:

```bash
uv run data-translate upload-datasets --upload daily_dialog_fr --config-root conf
```

Пробный экспорт всех настроенных загрузок:

```bash
uv run data-translate upload-datasets --all --config-root conf
```

Команда пишет результат в `data/hf_exports/<upload_id>` и печатает краткий отчет. Она не загружает данные в Hugging Face, пока не переданы `--push --yes`.

Загрузить один набор данных:

```bash
uv run data-translate upload-datasets --upload daily_dialog_fr --config-root conf --push --yes
```

Загрузить все настроенные наборы:

```bash
uv run data-translate upload-datasets --all --config-root conf --push --yes
```

Перед загрузкой проверьте авторизацию:

```bash
hf auth whoami
```

Текущие правила загрузки:

- `daily_dialog_fr`: обновляет `DeepPavlov/daily_dialog_fr` очищенным локальным переводом;
- `air_dialog_fr`: создает или обновляет `DeepPavlov/air_dialog_fr`;
- `canard_fr`: создает или обновляет `DeepPavlov/canard_fr` с `corpus`, `queries` и `qrels`;
- `clarqa_fr`: создает или обновляет `DeepPavlov/clarqa_fr` с `multi_turn` и `single_turn`;
- `multiwoz_fr`: создает или обновляет `DeepPavlov/multiwoz_fr`;
- `statcan_dialog_fr`: создает или обновляет `DeepPavlov/statcan_dialog_fr` с `queries` и `corpus`;
- `weblinx_fr`: создает или обновляет `DeepPavlov/weblinx_fr`;
- `faithdial_fr`: создает или обновляет `DeepPavlov/faithdial_fr`; текущий локальный результат содержит `history_fr` и `knowledge_fr`.

## Как собираются настройки

Итоговая настройка запуска собирается из нескольких слоев:

1. `conf/workflows/<workflow>.yaml`;
2. `conf/datasets/<dataset>.yaml`;
3. `conf/runs/<workflow>/<run>.yaml`, если указан `--run`;
4. переопределения `--set key=value`.

Посмотреть итоговые настройки:

```bash
make config-show WORKFLOW=translate DATASET=weblinx
make config-show WORKFLOW=evaluate DATASET=faithdial
```

Разовый запуск с переопределением:

```bash
uv run data-translate translate \
  --dataset weblinx \
  --set runtime.concurrency=8 \
  --set translation.backend.provider=deepl \
  --set translation.backend.api_key_env=DEEPL_API_KEY
```

Многоразовый набор параметров можно сохранить в `conf/runs/<workflow>/<run>.yaml`:

```yaml
run_name: deepl_fast
runtime:
  concurrency: 8
translation:
  backend:
    provider: deepl
    api_key_env: DEEPL_API_KEY
```

Запуск:

```bash
make translate DATASET=faithdial RUN=deepl_fast
```

## Где появляются файлы

- `airdialog`, `faithdial`, `weblinx`: исходные данные загружаются с Hugging Face;
- `globalwoz`: источник берется из Hugging Face `MultiWOZ-2.1`, готовый внешний перевод - из `data/external/globalwoz`;
- переводы сохраняются в `data/translated/...`;
- parquet-выгрузки сохраняются в `data/hf_exports/...`;
- отчеты и контрольные точки сохраняются в `results/...`.

## Оценка качества

Оценка качества отделена от перевода и не запускается автоматически после `translate`.

Обычная последовательность:

```bash
make translate DATASET=faithdial
make evaluate DATASET=faithdial
```

Настройки модели-оценщика берутся из:

- `conf/llm/translation_judge.yaml` для OpenRouter;
- `conf/llm/translation_judge_openai.yaml` для прямого вызова OpenAI API;
- `conf/prompts/...` для промптов оценки.

Пример с другой моделью через OpenRouter:

```bash
uv run data-translate evaluate \
  --dataset faithdial \
  --set llm.model=openai/gpt-4o-mini
```

Пример многоразовой настройки оценки:

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

Сохраните файл как `conf/runs/evaluate/gpt54mini.yaml`, затем запустите:

```bash
make evaluate DATASET=faithdial RUN=gpt54mini
```

## Сбои и продолжение работы

Запуски пишут контрольные точки в `results/...`. Если перевод прервался, повторный запуск с теми же настройками продолжит работу с уже сохраненного состояния, если сценарий поддерживает продолжение.
