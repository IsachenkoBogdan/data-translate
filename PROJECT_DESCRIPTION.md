# Описание проекта DialogMTEB

## Аннотация

Проект DialogMTEB направлен на расширение языкового покрытия диалоговых задач для оценки text embedding моделей. Такие модели используются в чат-ботах, ассистентах, поиске по истории диалогов, классификации намерений, retrieval и reranking ответов, поэтому качество их работы важно проверять не только на одиночных текстах, но и на данных с диалоговым контекстом.

Базовые embedding benchmark'и, включая [MTEB](https://arxiv.org/abs/2210.07316), покрывают широкий набор задач, но диалоговые сценарии остаются отдельной сложной областью. В диалоге модель должна учитывать историю, неполные реплики, кореференцию, прагматику, многозначность пользовательского запроса и связь между несколькими сообщениями. Кроме того, многие открытые диалоговые датасеты доступны прежде всего на английском языке, что ограничивает сравнимую оценку multilingual embedding моделей.

Цель командной работы - подготовить воспроизводимую основу для многоязычного DialogMTEB: перевести набор диалоговых датасетов на русский и французский языки, сохранить исходные схемы задач и опубликовать артефакты так, чтобы ими могли пользоваться другие исследователи. Важной частью работы было не только получение переводов, но и контроль того, что перевод не разрушает task schema, split'ы, идентификаторы, метки, qrels и специальные структурные поля.

В проекте были реализованы два взаимодополняющих подхода. Русскоязычная часть опиралась на notebook-based эксперименты, Yandex Translator и LLM-оценку качества перевода. Франкоязычная часть была оформлена как отдельный пакет `data-translate` с CLI, YAML-конфигами датасетов, стратегиями перевода, sanity checks, parquet export и загрузкой готовых датасетов в Hugging Face organization `DeepPavlov`.

Практический результат проекта - открытые репозитории с кодом и документацией, публичные Hugging Face датасеты, презентация для защиты и зафиксированное распределение вклада в команде. Это превращает перевод датасетов из ручного набора скриптов в воспроизводимый pipeline, который можно расширять на новые датасеты, языки и методы проверки качества.

## Проблематика

Embedding-модели активно используются в современных NLP-системах, но их качество на диалоговых задачах сложнее оценивать, чем на обычных sentence-level или document-level задачах. Диалоговые данные содержат историю взаимодействия, роли участников, структурные action-поля, ссылки, файлы, идентификаторы и разметку, которую нельзя переводить как обычный текст.

Если переводить такие датасеты вручную или разрозненными скриптами, возникает несколько рисков: меняется число строк в split'ах, теряются поля, ломаются списки реплик, переводятся служебные значения, нарушаются qrels или action sequence. В результате формально переведенный датасет может стать непригодным для честной оценки embedding моделей.

## Постановка задачи

Исследовательский вопрос проекта: можно ли расширить DialogMTEB на новые языки через автоматический перевод и контроль качества так, чтобы сохранить сопоставимость исходных задач?

В рамках этой постановки были выделены практические задачи:

- перевести набор диалоговых датасетов на русский и французский языки;
- сохранить исходные split'ы, схемы, labels, ids, qrels и task-specific поля;
- разработать проверки, которые находят структурные ошибки и подозрительные переводы до публикации;
- оформить результаты как открытые артефакты: GitHub repositories, README, Slidev-презентация и Hugging Face datasets;
- зафиксировать роли участников команды и воспроизводимый процесс работы.

## Описание технического решения

Русскоязычная часть проекта велась в репозитории [interpparietes/DialogMTEB](https://github.com/interpparietes/DialogMTEB). В ней использовались notebook-based пайплайны `translator_yandex_*`, перевод через Yandex Translator и оценка качества через `LLM_Evaluation.ipynb`. LLM-as-a-judge проверял качество по нескольким критериям: accuracy/completeness, grammar/orthography, naturalness/style.

Франкоязычная часть оформлена в репозитории [IsachenkoBogdan/data-translate](https://github.com/IsachenkoBogdan/data-translate). Пакет `data-translate` содержит CLI-команды для перевода, проверки, оценки, экспорта и загрузки датасетов. Dataset-specific логика вынесена в YAML-конфиги `conf/datasets`, а правила публикации - в `conf/uploads`.

Ключевая схема pipeline:

```text
dataset config
  -> translation strategy
  -> translated artifact
  -> check-translation
  -> parquet export
  -> Hugging Face upload
```

Для разных типов данных используются разные стратегии перевода: простые текстовые поля, списки реплик, диалоговые turns, вложенные структуры и deep-map стратегия, которая переводит все текстовые значения внутри ячейки. Отдельные guards сохраняют технические значения: URLs, filenames, paths, emails, hash-like ids, attachments и action syntax.

Модуль `check-translation` выполняет sanity checks перед загрузкой. Он проверяет совпадение числа строк и split'ов, наличие переведенных полей, пустые переводы, длины списков, подозрительно неизмененный английский текст, корректность WebLINX action sequence и alignment проблемные места на примере DailyDialog. Ложные warnings для технических строк подавляются отдельно, чтобы отчет фокусировался на реальных рисках перевода.

## Полученные результаты

Командный scope проекта включал 24 датасета и набора задач:

`atis_intents`, `banking77`, `vira-intent`, `CLINC150`, `HWU64`, `MTOPIntent`, `MASSIVE`, `X-RiSAWOZ`, `DailyDialog`, `statcan-dialogue-dataset-retrieval`, `WebLINX`, `FaithDial`, `Multi2WOZ`, `air-dialogue`, `CANARD`, `MANtIS`, `WoW`, `Clarqa`, `QReCC`, `TopiOCQA`, `Abg-CoQA`, `Coral`, `TREC iKAT 2023`, `DialogSum`.

Во французской части проекта подготовлены и загружены в Hugging Face следующие датасеты:

| Датасет | Hugging Face repository | Статус |
| --- | --- | --- |
| DailyDialog | [DeepPavlov/daily_dialog_fr](https://huggingface.co/datasets/DeepPavlov/daily_dialog_fr) | Переведен и загружен |
| StatCan Dialogue | [DeepPavlov/statcan_dialog_fr](https://huggingface.co/datasets/DeepPavlov/statcan_dialog_fr) | Переведен и загружен |
| WebLINX | [DeepPavlov/weblinx_fr](https://huggingface.co/datasets/DeepPavlov/weblinx_fr) | Переведен и загружен |
| FaithDial | [DeepPavlov/faithdial_fr](https://huggingface.co/datasets/DeepPavlov/faithdial_fr) | Переведен и загружен; текущий artifact содержит `history_fr` и `knowledge_fr` |
| MultiWOZ / Multi2WOZ | [DeepPavlov/multiwoz_fr](https://huggingface.co/datasets/DeepPavlov/multiwoz_fr) | Переведен и загружен |
| AirDialog | [DeepPavlov/air_dialog_fr](https://huggingface.co/datasets/DeepPavlov/air_dialog_fr) | Переведен и загружен |
| CANARD | [DeepPavlov/canard_fr](https://huggingface.co/datasets/DeepPavlov/canard_fr) | Переведен и загружен |
| ClarQA | [DeepPavlov/clarqa_fr](https://huggingface.co/datasets/DeepPavlov/clarqa_fr) | Переведен и загружен |

В процессе остаются French translations для `MANtIS`, `WoW`, `Abg-CoQA` и `Coral`. Для них подготовлены конфиги и дальнейшая загрузка планируется после завершения перевода и прохождения проверок.

Дополнительные публичные артефакты:

- репозиторий французского pipeline: [IsachenkoBogdan/data-translate](https://github.com/IsachenkoBogdan/data-translate);
- репозиторий русскоязычной части: [interpparietes/DialogMTEB](https://github.com/interpparietes/DialogMTEB);
- Slidev-презентация: [`presentation/slides.md`](presentation/slides.md);
- PDF для защиты: [`presentation/DialogMTEB_project_practice.pdf`](presentation/DialogMTEB_project_practice.pdf).

## Дальнейшие планы по развитию

Дальнейшая работа состоит из нескольких направлений:

- завершить и загрузить `MANtIS`, `WoW`, `Abg-CoQA` и `Coral` во французской части;
- добавить human audit для небольшого in-domain bilingual dev set;
- добавить второй уровень LLM-проверки для подозрительно непереведенного текста;
- интегрировать переведенные датасеты в полноценный multilingual DialogMTEB evaluation;
- расширить pipeline на новые языки и новые типы диалоговых задач;
- подготовить результаты как open-source benchmark artifact для дальнейших исследований и возможной публикации.

## Команда и распределение задач

Руководитель проекта: Леднева Дарья. Зоны ответственности: постановка научной задачи, консультации по методологии DialogMTEB/MTEB, рецензирование результатов и контроль исследовательской логики.

| Участник | Степень участия | Роль и зона ответственности | Основные артефакты |
| --- | --- | --- | --- |
| Кремнева Полина | 50% | Русскоязычная часть проекта; перевод датасетов с английского на русский; notebook-based эксперименты; настройка Yandex Translator; LLM-as-a-judge оценка качества перевода | [interpparietes/DialogMTEB](https://github.com/interpparietes/DialogMTEB), notebooks перевода и оценки |
| Богдан Исаченко | 50% | Франкоязычная часть проекта; перевод датасетов с английского на французский; разработка `data-translate`; YAML-конфиги; translation strategies; `check-translation`; parquet export; загрузка датасетов в Hugging Face | [IsachenkoBogdan/data-translate](https://github.com/IsachenkoBogdan/data-translate), `conf/datasets`, `conf/uploads`, `presentation/`, French HF datasets |

В защите команда распределяет рассказ по зонам ответственности: Полина представляет русскоязычный перевод и LLM-оценку, Богдан представляет воспроизводимый French pipeline, контроль качества, Hugging Face uploads и инженерную часть артефактов.
