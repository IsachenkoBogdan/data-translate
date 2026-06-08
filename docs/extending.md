# Расширение проекта

Эта страница описывает четыре частые задачи:

- добавить новый набор данных;
- добавить правило загрузки в Hugging Face;
- добавить нового поставщика перевода;
- добавить нового поставщика или адаптер языковой модели для оценки.

Проект уже разделен на точки расширения, поэтому новые интеграции лучше добавлять по существующим шаблонам.

## Добавить новый набор данных

### 1. Создать `conf/datasets/<dataset>.yaml`

Начните с наиболее похожего существующего файла.

Минимальный пример для источника с Hugging Face:

```yaml
dataset_id: mydataset
source:
  hf_dataset_id: org/mydataset
  hf_revision: 0123456789abcdef
artifacts:
  translated_basename: org_mydataset
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
  domain: short description of what should stay invariant
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

### 2. Выбрать стратегию перевода

Используйте:

- `text` для одного текстового поля;
- `text_list` для списка строк;
- `dialog_turns_content` для списка объектов-реплик;
- `weblinx_query` для записей WebLINX с трассой действий;
- `nested_text_fields` для заранее указанных путей во вложенной структуре;
- `deep_map_texts` для перевода всех текстовых значений внутри вложенной ячейки.

Если ни одна стратегия не подходит, добавьте новую. Не стоит подгонять сложную структуру под неподходящую стратегию.

Реестр стратегий:

- [registry.py](../src/data_translate/domain/translation_strategies/registry.py)

### 3. Решить: `translate` или `reformat`

Используйте `translate`, если проект сам переводит исходные данные.

Используйте `reformat`, если:

- внешний перевод уже существует;
- его нужно выровнять с исходной схемой;
- внешний файл не является источником истины.

Пример:

- [globalwoz.yaml](../conf/datasets/globalwoz.yaml)

### 4. Проверить настройки перед запуском

```bash
make config-show WORKFLOW=translate DATASET=mydataset
make config-show WORKFLOW=evaluate DATASET=mydataset
```

### 5. Запустить перевод и оценку

```bash
make translate DATASET=mydataset
make evaluate DATASET=mydataset
```

### 6. Добавить правило загрузки

Создайте `conf/uploads/<upload_id>.yaml`, когда переведенный результат уже существует. Эти файлы описывают parquet-структуру, которую использует организация DeepPavlov на Hugging Face.

Ориентиры:

- `daily_dialog_fr.yaml` для одного стандартного поднабора `data/`;
- `canard_fr.yaml` для поисковых наборов с `corpus`, `queries` и `qrels`;
- `clarqa_fr.yaml` для одного репозитория с несколькими поднаборами;
- `statcan_dialog_fr.yaml` для сериализованного диалогового содержимого, где `content_fr` заменяет `content`.

Пробный экспорт:

```bash
uv run data-translate upload-datasets --upload mydataset_fr --config-root conf
```

Публикуйте только после просмотра сгенерированных parquet-файлов:

```bash
uv run data-translate upload-datasets --upload mydataset_fr --config-root conf --push --yes
```

## Добавить новую стратегию перевода

Новая стратегия нужна, когда форма поля или сохраняемые инварианты заметно отличаются от уже поддержанных случаев.

### 1. Реализовать файл стратегии

Файл должен лежать в:

- `src/data_translate/domain/translation_strategies`

Стратегии нужны:

- функция перевода с сигнатурой, совместимой с текущими стратегиями;
- проверка входной формы.

Файлы-ориентиры:

- [text.py](../src/data_translate/domain/translation_strategies/text.py)
- [dialog.py](../src/data_translate/domain/translation_strategies/dialog.py)
- [weblinx.py](../src/data_translate/domain/translation_strategies/weblinx.py)

### 2. Зарегистрировать стратегию

Обновите:

- [registry.py](../src/data_translate/domain/translation_strategies/registry.py)

Нужно добавить обе карты:

- `STRATEGIES`;
- `INPUT_VALIDATORS`.

### 3. Использовать стратегию в настройках набора данных

```yaml
rules:
  - source: my_field
    target: my_field_fr
    strategy: my_strategy
```

### 4. Добавить тесты

Хорошие тесты обычно проверяют:

- корректную входную форму;
- некорректную входную форму;
- сохранение инвариантов;
- многострочный текст и экранирование, если формат структурированный.

## Добавить нового поставщика перевода

Этот путь подходит для нового переводчика, например еще одного HTTP-сервиса.

### 1. Добавить модель настроек

Файл:

- [models_dataset_translation.py](../src/data_translate/config/models_dataset_translation.py)

Шаблон:

```python
class MyBackendModel(BaseModel):
    provider: Literal["mybackend"] = "mybackend"
    api_key_env: str = Field(min_length=1)
```

Затем включите модель в `TranslationBackendModel`.

### 2. Реализовать адаптер

Файл должен лежать в:

- `src/data_translate/adapters`

Адаптер должен удовлетворять протоколу `TranslationAdapter`:

- [translation_base.py](../src/data_translate/adapters/translation_base.py)

Обязательные методы:

- `translate(text, use_cache=...) -> TranslationResult`;
- `close()`.

### 3. Подключить адаптер к фабрике

Файл:

- [translation_factory.py](../src/data_translate/adapters/translation_factory.py)

Нужно добавить:

- импорт;
- ветку `isinstance(...)`;
- нормализацию языковых кодов, если поставщик требует особый формат.

### 4. Добавить набор параметров запуска

Пример:

```yaml
run_name: mybackend
translation:
  backend:
    provider: mybackend
    api_key_env: MYBACKEND_API_KEY
```

Путь:

- `conf/runs/translate/mybackend.yaml`

### 5. Протестировать

Минимум:

- проверка настроек;
- успешный путь адаптера;
- путь ошибки адаптера;
- создание адаптера через фабрику.

## Добавить нового поставщика модели-оценщика

Это относится к оценке качества, а не к переводу наборов данных.

### 1. Решить, достаточно ли LiteLLM

Если поставщик работает через LiteLLM, самый простой путь:

- добавить сопоставление поставщика при необходимости;
- продолжить использовать [litellm_adapter.py](../src/data_translate/adapters/litellm_adapter.py).

Если требуется особое поведение, создайте новый адаптер с интерфейсом:

- [llm_base.py](../src/data_translate/adapters/llm_base.py)

### 2. Подключить адаптер

Файл:

- [llm_factory.py](../src/data_translate/adapters/llm_factory.py)

Варианты:

- сопоставить нового поставщика с существующим LiteLLM-сборщиком;
- добавить новый сборщик, который возвращает собственный адаптер.

### 3. Добавить настройку языковой модели

Пример:

```yaml
provider: myjudge
api_key_env: MYJUDGE_API_KEY
model: my-model
```

Путь:

- `conf/llm/myjudge.yaml`

### 4. Добавить проверку оценки

Минимум:

- проверка настроек;
- создание адаптера;
- обработка корректного ответа;
- обработка ошибки или некорректного ответа.
