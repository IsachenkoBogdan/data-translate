# Quality configs

`conf/quality/*.yaml` описывает проверки для случаев, когда исходный и
переведенный наборы данных уже опубликованы или были получены не через
локальный layout `data/translated/...`.

Типовой запуск:

```bash
make check-translation QUALITY=multiwoz_fr MAX_ROWS_PER_SPLIT=1000
uv run data-translate check-translation --quality topiocqa_fr --max-rows-per-split 1000
```

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
