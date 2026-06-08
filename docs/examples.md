# Примеры

На этой странице собраны практические шаблоны настроек. Их можно копировать и адаптировать под новый набор данных.

## 1. Одно текстовое поле

Используйте этот вариант, когда в каждой строке есть одно обычное текстовое поле.

Пример исходной строки:

```json
{
  "id": "42",
  "text": "Hello, how are you?"
}
```

Настройка:

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

Запуск:

```bash
make translate DATASET=my_text_dataset
make check-translation DATASET=my_text_dataset
make evaluate DATASET=my_text_dataset
```

## 2. Список реплик

Используйте `text_list`, когда поле содержит список строк.

Пример:

```json
{
  "history": [
    "Hi, I need help with my booking.",
    "Sure, what is your booking reference?"
  ]
}
```

Настройка:

```yaml
translation:
  rules:
    - source: history
      target: history_fr
      strategy: text_list
      cache: true
evaluation:
  field_pairs:
    - name: history_fr
      source_dataset: source
      source_field: history
      source_format: list
      translation_dataset: translation
      translation_field: history_fr
      translation_format: list
```

`check-translation` дополнительно проверит, что длина исходного и переведенного списков совпадает.

## 3. Диалоговые ходы с ролями

Используйте `dialog_turns_content`, когда нужно переводить только текст реплики, сохранив роль участника.

Пример:

```json
{
  "text": [
    {"role": "user", "content": "I need a flight to Paris."},
    {"role": "agent", "content": "What date do you prefer?"}
  ]
}
```

Настройка:

```yaml
translation:
  rules:
    - source: text
      target: text
      strategy: dialog_turns_content
      cache: true
```

Результат сохраняет `role`, а `content` заменяет на перевод.

## 4. Вложенные поля по путям

Используйте `nested_text_fields`, когда переводить нужно не всю структуру, а только конкретные пути.

Пример:

```json
{
  "turn": {
    "question": "Who wrote the book?",
    "answers": [
      {"answer": "Jane Austen", "id": "a1"}
    ]
  }
}
```

Настройка:

```yaml
translation:
  rules:
    - source: turn
      target: turn_fr
      strategy: nested_text_fields
      options:
        paths:
          - question
          - answers[].answer
```

Идентификаторы и другие поля вне указанных путей останутся без изменений.

## 5. Перевод всех текстовых значений во вложенной ячейке

Используйте `deep_map_texts`, когда структура сложная и заранее перечислять все текстовые пути неудобно.

Пример:

```json
{
  "history_turns": [
    {
      "id": "t1",
      "question": "What did the user ask?",
      "answers": ["A refund", "A delivery date"]
    }
  ]
}
```

Настройка:

```yaml
translation:
  rules:
    - source: history_turns
      target: history_turns
      strategy: deep_map_texts
      options:
        exclude_keys:
          - id
```

Стратегия проходит по вложенной структуре, переводит строковые значения и сохраняет исходный тип контейнеров. Ключи из `exclude_keys` не переводятся.

## 6. WebLINX с действиями

Используйте `weblinx_query`, когда текст смешан со служебными вызовами действий.

Пример:

```text
User: find the cheapest ticket
Agent: click(node="button.search")
Agent: say(utterance="Here are the cheapest options.")
```

Настройка:

```yaml
translation:
  rules:
    - source: query
      target: query_fr
      strategy: weblinx_query
      options:
        translate_agent_say_utterance: true
```

Стратегия сохраняет порядок действий и служебный синтаксис. Это важно, потому что такие поля используются не только как текст, но и как трасса выполнения.

## 7. Внешний готовый перевод

Используйте `reformat`, если перевод уже получен другим способом и его нужно выровнять с исходной схемой.

Пример:

```yaml
dataset_id: globalwoz
source:
  hf_dataset_id: DeepPavlov/MultiWOZ-2.1
artifacts:
  external_root: data/external/globalwoz
  translated_basename: globalwoz_candidates
reformat:
  candidates:
    FF: FF/F&F_fr.json
```

Запуск:

```bash
make inspect-source DATASET=globalwoz RUN=ff
make reformat DATASET=globalwoz RUN=ff
make check-translation DATASET=globalwoz RUN=ff
```

## 8. Правило загрузки в Hugging Face

После перевода добавьте файл `conf/uploads/<upload_id>.yaml`.

Пример для одного parquet-поднабора:

```yaml
upload_id: my_text_dataset_fr
target:
  repo_id: DeepPavlov/my_text_dataset_fr
  private: false
source:
  artifact_path: data/translated/my_text_dataset
exports:
  - name: data
    split: train
    columns:
      text: text_fr
validation:
  min_rows: 1
```

Пробный экспорт:

```bash
uv run data-translate upload-datasets --upload my_text_dataset_fr --config-root conf
```

Загрузка:

```bash
uv run data-translate upload-datasets --upload my_text_dataset_fr --config-root conf --push --yes
```

## 9. Быстрая проверка перед публикацией

Перед загрузкой полезно выполнить короткий цикл:

```bash
make check-translation DATASET=my_text_dataset MAX_ROWS_PER_SPLIT=1000
uv run data-translate upload-datasets --upload my_text_dataset_fr --config-root conf
```

Если отчет чистый и parquet-файлы выглядят правильно, можно запускать команду с `--push --yes`.
