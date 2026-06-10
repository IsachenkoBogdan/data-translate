# data-translate

`data-translate` - локальный пакет для перевода диалоговых наборов данных, проверки качества перевода, подготовки выгрузок в формате parquet для Hugging Face Hub и запуска оценочных экспериментов.

## Артефакт проектной практики

Этот репозиторий является одним из технических артефактов проектной практики по DialogMTEB. DialogMTEB - направление наборов оценки для моделей векторных представлений текста на диалоговых задачах: классификации, поиске, повторном ранжировании, парной классификации и оценке смысловой близости. Практическая цель работы - расширить набор оценки за пределы английского языка, подготовив переведенные диалоговые наборы данных с сохранением исходных схем, меток, разбиений и совместимости с оценкой.

Этот репозиторий закрывает французскую часть проекта: воспроизводимые настройки перевода, переиспользуемые стратегии перевода, проверки качества, экспорт в parquet и автоматизацию загрузки в Hugging Face Hub. Сопутствующий репозиторий [interpparietes/DialogMTEB](https://github.com/interpparietes/DialogMTEB) закрывает интерактивные исследовательские сценарии и русскоязычную часть проекта.

Основные публичные артефакты:
- код и воспроизводимый конвейер перевода: этот репозиторий
- текстовое описание проекта для Talent Track: [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md)
- загруженные французские наборы данных: репозитории Hugging Face из таблицы статуса ниже
- презентация и видео-питч: отдельные артефакты для Talent Track

## Команда и распределение задач

Руководитель проекта: Леднева Дарья. Зона ответственности руководителя: постановка научной задачи, консультации по методологии DialogMTEB/MTEB, рецензирование результатов и контроль исследовательской логики.

| Участник | Степень участия | Зоны ответственности | Основные артефакты |
| --- | --- | --- | --- |
| Кремнева Полина | 50% | Русскоязычная часть проекта; перевод наборов данных с английского на русский; интерактивные исследовательские сценарии; оценка качества перевода с помощью языковой модели и промпты для проверки | [interpparietes/DialogMTEB](https://github.com/interpparietes/DialogMTEB), русские переводы и материалы оценки |
| Богдан Исаченко | 50% | Франкоязычная часть проекта; унифицированная инфраструктура перевода; команды, настройки наборов данных, стратегии перевода, статические проверки, экспорт в parquet и загрузка в Hugging Face | этот репозиторий, `conf/datasets`, `conf/uploads`, `check-translation`, `upload-datasets`, французские наборы Hugging Face |

Для защиты рекомендуется отразить это же разделение в презентации отдельным слайдом: Полина показывает русскоязычный перевод и оценку языковой моделью, Богдан показывает французский конвейер перевода, контроль качества, загрузку наборов данных и воспроизводимость.

Текущий объем работ:
- перевод диалоговых наборов данных на французский без изменения схемы задач
- инспекция и приведение к единому формату готовых внешних переводов
- экспорт переведенных результатов в структуру parquet, используемую организацией Hugging Face `DeepPavlov`
- запуск оценки с помощью языковой модели и оценочных экспериментов

Основной пакет:
- `src/data_translate`

Документация:
- [PROJECT_DESCRIPTION.md](PROJECT_DESCRIPTION.md)
- [docs/usage.md](docs/usage.md)
- [docs/reference.md](docs/reference.md)
- [docs/extending.md](docs/extending.md)
- [docs/examples.md](docs/examples.md)

Команды пакета:

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

Типовой сценарий:

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
- наборы данных загружаются с Hugging Face, если в настройках задан `source.hf_dataset_id`
- `globalwoz` - основное исключение с внешним источником перевода; для него используется `reformat`, а не `translate`
- `check-translation` - проверка перед загрузкой: схема, число строк, длины списков, пустые переводы, подозрительный непереведенный английский текст и сохранение последовательностей действий WebLINX
- технические значения вроде ссылок, имен файлов, вложений, путей, почтовых адресов и похожих на хеши идентификаторов игнорируются в предупреждениях о неизмененном тексте
- `upload-datasets` читает `conf/uploads/*.yaml`, экспортирует локальные переводы в parquet под `data/hf_exports` и загружает в Hugging Face только с `--push --yes`
- оценка качества - отдельный сценарий; она не запускается автоматически после перевода
- OpenRouter поддерживается для моделей-оценщиков через `conf/llm/translation_judge.yaml`

Статус наборов данных:

Актуально на 10 июня 2026 года: французские версии всех завершенных наборов опубликованы в организации `DeepPavlov` на Hugging Face.

| Исходный набор данных | Локальный идентификатор | Французский репозиторий Hugging Face | Статус |
| --- | --- | --- | --- |
| DailyDialog Manually Labelled Multi-turn Dialogue Dataset | `daily_dialog` | [DeepPavlov/daily_dialog_fr](https://huggingface.co/datasets/DeepPavlov/daily_dialog_fr) | Переведен и загружен |
| statcan-dialogue-dataset-retrieval | `statcan-dialogue-dataset-retrieval` | [DeepPavlov/statcan_dialog_fr](https://huggingface.co/datasets/DeepPavlov/statcan_dialog_fr) | Переведен и загружен |
| WebLINX | `weblinx` | [DeepPavlov/weblinx_fr](https://huggingface.co/datasets/DeepPavlov/weblinx_fr) | Переведен и загружен |
| FaithDial | `faithdial` | [DeepPavlov/faithdial_fr](https://huggingface.co/datasets/DeepPavlov/faithdial_fr) | Переведен и загружен; текущий результат содержит `history_fr` и `knowledge_fr` |
| Multi2WOZ / MultiWOZ | `globalwoz` | [DeepPavlov/multiwoz_fr](https://huggingface.co/datasets/DeepPavlov/multiwoz_fr) | Переведен и загружен |
| air-dialogue | `airdialog` | [DeepPavlov/air_dialog_fr](https://huggingface.co/datasets/DeepPavlov/air_dialog_fr) | Переведен и загружен |
| CANARD | `canard_queries` | [DeepPavlov/canard_fr](https://huggingface.co/datasets/DeepPavlov/canard_fr) | Переведен и загружен |
| ClarQA | `clarqa_multi_turn`, `clarqa_single_turn` | [DeepPavlov/clarqa_fr](https://huggingface.co/datasets/DeepPavlov/clarqa_fr) | Переведен и загружен |
| MANtIS | `mantis` | [DeepPavlov/mantis_fr](https://huggingface.co/datasets/DeepPavlov/mantis_fr) | Переведен и загружен; `check-translation`: 0 ошибок, 0 предупреждений |
| Wizard of Wikipedia / WoW | `wizard_of_wikipedia` | Планируется | Перевод в процессе; будет загружен после завершения и проверок |
| Abg-CoQA | `coqa_abg` | [DeepPavlov/coqa_abg_fr](https://huggingface.co/datasets/DeepPavlov/coqa_abg_fr) | Переведен и загружен |
| Coral | `coral_*` | Планируется | Перевод в процессе; настройки подготовлены, загрузка после завершения и проверок |

План дальнейших улучшений:
- добавить `mt-metrics-eval` как внешний набор для калибровки качества моделей-оценщиков на стандартных данных машинного перевода с человеческими оценками
- сохранить оценочные эксперименты в стиле WMT, но валидировать их небольшой двуязычной проверкой внутри домена диалогов
- добавить опциональную проверку второго уровня с помощью языковой модели: быстрый проверяющий модуль собирает подозрительные кандидаты, а модель решает, является ли текст действительно непереведенным английским, и возвращает структурированную замену на французском
- перейти к оценке реплик по рубрике, используя историю диалога как контекст
- показывать качество модели-оценщика по языковой паре и диапазону качества, а не только одной глобальной корреляцией
- рассматривать оптимизацию промптов через DSPy как отдельный поздний эксперимент после появления небольшой размеченной выборки внутри домена

Структура настроек:
- `conf/datasets` описания наборов данных
- `conf/uploads` правила экспорта в parquet и загрузки в Hugging Face
- `conf/workflows` значения по умолчанию для сценариев
- `conf/runs` наборы параметров запусков
- `conf/llm`, `conf/runtime`, `conf/prompts` настройки среды выполнения и оценки

Структура кода:
- `src/data_translate/config` типизированные модели настроек и сборщики
- `src/data_translate/workflows` точки входа сценариев
- `src/data_translate/services` сервисы координации
- `src/data_translate/domain` основная логика перевода и оценки
- `src/data_translate/adapters` адаптеры перевода и языковых моделей
- `src/data_translate/engine` результаты запусков, отчеты, манифесты и контрольные точки
