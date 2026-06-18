# Quality configs

`conf/quality/*.yaml` описывает проверки для случаев, когда исходный и
переведенный наборы данных уже опубликованы или были получены не через
локальный layout `data/translated/...`.

Типовой запуск:

```bash
make check-translation QUALITY=multiwoz_fr MAX_ROWS_PER_SPLIT=1000
uv run data-translate check-translation --quality topiocqa_fr --max-rows-per-split 1000
```

Сводный аудит всех опубликованных переводов из организации DeepPavlov запускается
отдельным скриптом. Он сравнивает опубликованные переводы с исходными наборами
данных по плану `conf/quality/hf_audit_plan.csv` и проверяет все строки без
семплирования:

```bash
uv run python scripts/audit_hf_translation_quality.py --reset
```

План включает французские `FaithDial`, `Multi2WOZ` и `Coral`. Для `Coral`
ожидается опубликованный набор `DeepPavlov/coral_fr` с конфигурациями `corpus`,
`qrels` и `queries`; если репозиторий еще не виден в Hugging Face Dataset
Viewer, соответствующие строки аудита будут помечены как `missing_split`.
Флаг `--exclude` нужен только для разового исключения дополнительных пар
`DATASET:LANG`. Результаты пишутся в `reports/translation_coverage/`.

Строки со статусом `missing` считаются проблемными: ожидаемый перевод не найден,
репозиторий пуст или конфиг для пары `dataset/language` отсутствует. Строки
`metadata_only` нейтральные: это служебные части вроде `qrels`, ranking labels
или retrieval metadata, где нет переводимого текстового поля; переводимые части
того же набора данных должны быть представлены отдельными auditable-строками.

Поля конфига:

- `source`: исходный набор данных в том же формате, что и `source` в
  `conf/datasets/*.yaml`;
- `translation`: перевод, который нужно проверить;
- `split_map`: необязательное соответствие `source split -> translated split`;
- `rules`: явные пары полей `source -> target`;
- `rules_from`: переиспользование правил из существующего dataset-конфига. Если
  указан `upload_id`, `replace_columns` из `conf/uploads` применяются к правилам,
  чтобы локальные поля вроде `text_fr` сравнивались с опубликованными полями
  вроде `text`.

В `hf_audit_plan.csv` нет режима проверки "только перевод": каждая переводимая
колонка либо сравнивается с исходным Hugging Face набором данных, либо с
исходной колонкой внутри того же опубликованного набора. Служебные конфиги без
переводимых текстовых колонок, например `qrels`, помечены как `metadata_only`.
