# Справочник

## Настройка набора данных

Каждый файл `conf/datasets/<dataset>.yaml` описывает источник данных, правила перевода, оценку и, при необходимости, приведение внешнего перевода к схеме проекта.

Минимальный пример:

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

Основные разделы:

- `source`: откуда загружается исходный набор данных;
- `artifacts`: имена и корни выходных директорий;
- `translation`: правила перевода и используемый переводчик;
- `evaluation`: настройка модели-оценщика и пар полей;
- `reformat`: правила приведения внешнего перевода к локальной схеме.

Типовой источник с Hugging Face:

```yaml
source:
  hf_dataset_id: DeepPavlov/FaithDial-ru
  hf_revision: ed49d9732196e96d5291e11cfa416083b8ff699e
```

Источник с внешним готовым переводом:

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

## Стратегии перевода

Стратегия определяет, как интерпретировать значение поля перед отправкой текста переводчику.

### `text`

Используется для одного строкового поля.

Ожидаемая форма:

- строка или значение, приводимое к строке.

Пример:

```yaml
- source: knowledge
  target: knowledge_fr
  strategy: text
```

### `text_list`

Используется для списка коротких текстовых элементов. Сначала система пытается перевести весь список с разметкой элементов, затем при ошибке разбора переводит элементы по одному.

Ожидаемая форма:

- список строковых элементов.

Пример:

```yaml
- source: history
  target: history_fr
  strategy: text_list
```

### `dialog_turns_content`

Используется для списка объектов-реплик, где переводить нужно только поле `content`, а роли участников должны сохраниться.

Ожидаемая форма:

- список объектов;
- в каждом объекте есть поле `content`.

Пример:

```yaml
- source: text
  target: text
  strategy: dialog_turns_content
```

Эта стратегия используется в `airdialog`.

### `weblinx_query`

Используется для записей WebLINX, где естественный язык смешан с вызовами действий.

Что делает стратегия:

- переводит блоки `User:`;
- при включенной настройке переводит естественный язык внутри `Agent: say(..., utterance="...")`;
- сохраняет служебный синтаксис действий, число строк и порядок действий;
- оставляет действия, похожие на DOM-команды или код, без изменений.

Настройка:

```yaml
options:
  translate_agent_say_utterance: true
```

### `nested_text_fields`

Используется для вложенных словарей и списков, когда нужно перевести только заранее указанные текстовые пути.

Пример:

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

Используется, когда внутри вложенной ячейки нужно перевести все текстовые значения, сохранив исходную структуру.

Пример:

```yaml
- source: history_turns
  target: history_turns
  strategy: deep_map_texts
  options:
    exclude_keys:
      - id
```

Эта стратегия используется в `coqa_abg`.

## Проверка стратегий

У каждой стратегии есть проверка входных данных. Регистрация функций перевода и проверок находится в:

- [registry.py](../src/data_translate/domain/translation_strategies/registry.py)

Добавление стратегии состоит из двух обязательных шагов:

- реализовать функцию перевода;
- реализовать проверку входной формы и зарегистрировать оба имени.

## Переводчики

Переводчик настраивается в разделе `translation.backend`.

### `google`

Базовый вариант для массового перевода.

```yaml
backend:
  provider: google
```

### `deepl`

HTTP-переводчик с ключом API и опциональной формальностью.

```yaml
backend:
  provider: deepl
  api_key_env: DEEPL_API_KEY
```

### `yandex`

HTTP-переводчик с ключом API и идентификатором каталога.

```yaml
backend:
  provider: yandex
  api_key_env: YANDEX_API_KEY
  folder_id_env: YANDEX_FOLDER_ID
```

Модели настроек переводчиков описаны в:

- [models_dataset_translation.py](../src/data_translate/config/models_dataset_translation.py)

Создание переводчика выполняется в:

- [translation_factory.py](../src/data_translate/adapters/translation_factory.py)

## Адаптеры языковых моделей

Модели-оценщики настраиваются в `conf/llm/*.yaml`.

Поддерживаемые поставщики:

- `openrouter`;
- `openai`.

Оба проходят через адаптер на основе LiteLLM.

Пример OpenRouter:

```yaml
provider: openrouter
api_key_env: OPENROUTER_API_KEY
base_url: https://openrouter.ai/api/v1
model: openai/gpt-4o-mini
```

Пример OpenAI:

```yaml
provider: openai
api_key_env: OPENAI_API_KEY
model: gpt-4o-mini
```

Интерфейс адаптера:

- [llm_base.py](../src/data_translate/adapters/llm_base.py)

Текущая реализация на LiteLLM:

- [litellm_adapter.py](../src/data_translate/adapters/litellm_adapter.py)

Маршрутизация поставщиков:

- [llm_factory.py](../src/data_translate/adapters/llm_factory.py)

## Реестр сценариев

Зарегистрированные сценарии:

- `translate`;
- `evaluate`;
- `benchmark-judge`;
- `reformat`;
- `inspect-source`;
- `upload-datasets`;
- `config-show`.

Реестр находится в:

- [registry.py](../src/data_translate/workflows/registry.py)

## Выгрузки в Hugging Face

Правила выгрузки находятся в `conf/uploads/*.yaml`. Они задают целевой репозиторий, локальные источники, структуру parquet-файлов и проверки.

Минимальный пример:

```yaml
upload_id: daily_dialog_fr
target:
  repo_id: DeepPavlov/daily_dialog_fr
  private: false
source:
  artifact_path: data/translated/daily_dialog
exports:
  - name: data
    split: train
    columns:
      dialog: dialog_fr
validation:
  min_rows: 1
```

Сухой запуск ничего не отправляет в Hugging Face:

```bash
uv run data-translate upload-datasets --upload daily_dialog_fr --config-root conf
```

Публикация требует явного подтверждения:

```bash
uv run data-translate upload-datasets --upload daily_dialog_fr --config-root conf --push --yes
```
