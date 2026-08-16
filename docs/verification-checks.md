# Verification Checks — реестр проверок

Минимальный набор **детерминированных** проверок (`verify`), которые может использовать скилл. Реестр расширяемый. Скилл ссылается на проверки по `id` в поле `verify_checks[]`.

> Все проверки — это код, не LLM. При провале хотя бы одной `verify` = fail; движок кормит список ошибок обратно в агент (retry, до `max_retries`).

## Формат записи в конфиге скилла

```
verify_checks: [
  { check: "non_empty" },
  { check: "markdown_well_formed" },
  { check: "has_section", params: { heading: "Тезисы" } }
]
```

## Базовые (общие)
- `non_empty` — результат непустой после `trim()`.
- `min_length` — длина не меньше границы. `params: { min, unit?: "chars"|"lines" }`.
- `max_length` — длина не больше границы. `params: { max, unit?: "chars"|"lines" }`.
- `regex_matches` — содержит совпадение с регулярным выражением. `params: { pattern }`.
- `no_leftover_placeholders` — нет незаполненных плейсхолдеров (`{...}`, `<...>`, `TODO`).

## Markdown
- `markdown_well_formed` — парсится как валидный markdown без ошибок.
- `has_section` — есть заголовок. `params: { heading, level? }`.
- `has_field` — есть строка вида `Ключ: значение`. `params: { key }`.
- `table_parses` — markdown-таблица парсится в строки/колонки (минимум 1 строка данных). `params: { min_rows?, min_cols? }`.

## Структуры (на будущее — закладываем идентификаторы)
- `json_valid` — результат — валидный JSON.
- `json_schema` — соответствует JSON-Schema. `params: { schema }`.
- `archimate_well_formed` — well-formed XML (для будущего экспорта в ArchiMate).

## Правила расширения
1. Завести `id` (snake_case), краткое описание, набор `params`.
2. Зарегистрировать реализацию в коде (registry: `id -> fn(text, params) -> bool | {ok, reason}`).
3. Добавить запись в этот файл.
4. Проверки остаются детерминированными; семантика — LLM-судья (ADR-0020), не часть этого реестра.
