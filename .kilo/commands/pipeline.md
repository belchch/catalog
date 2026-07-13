---
description: "Автономная ночная цепочка: проходит валидные шаги из папки, каждый шаг — генератор↔ревьюер (до 5 циклов) в общий PR. Никогда не останавливается, мусор игнорирует."
agent: code
---
Запусти автономную цепочку шагов. ПАПКА ШАГОВ (обязательный): $1
Полная строка: $ARGUMENTS

## Подготовка
1. STEPS_DIR = $1. Если пусто/не существует — выведи диагностику и закончи (это не «остановка посреди», это неверный запуск).
2. SLUG = basename(STEPS_DIR). BRANCH = pipeline/<SLUG>. База = master.
3. STATE = .kilo/.pipeline-state.json. Прочитай, если есть: { branch, pr_url, pr_number, steps{} }.
4. Общая ветка (одна на весь pipeline):
   - git fetch origin; git checkout master; (git pull --ff-only origin master если трекается).
   - git checkout <BRANCH> если существует, иначе git checkout -b <BRANCH> от master.
   - git push -u origin <BRANCH> (при первом пуше).
5. PR: gh pr list --head <BRANCH> --state open --json number,url. Если есть — запомни PR_NUMBER/PR_URL. Иначе PR создаст step-runner на первом шаге.

## Сканирование шагов (мусор игнорируй)
- Собери файлы STEPS_DIR (нерекурсивно).
- ВАЛИДНЫЙ ШАГ = *.md, не скрытый (имя не начинается с .), не README*/index*, непустой (>1 непустой строки после обрезки).
- Всё остальное = МУСОР → игнорируй (можно записать в state как ignored для аудита, шагом не считать).
- Отсортируй валидные шаги по имени (natural: step-01, step-02 …).

## Алгоритм (СТРОГО, НИКОГДА не останавливайся между шагами)
Для каждого ШАГА по порядку:
1. ПРОПУСК: если STATE.steps[ШАГ].status ∈ {done, failed} → пропусти (уже выполнено/исчерпано).
2. BASE_SHA = git rev-parse HEAD (baseline ревью этого шага). Запиши в state[ШАГ].base_sha.
3. Task → step-runner: «STEPS_DIR=<…>, STEP=<путь к файлу шага>, BRANCH=<BRANCH>, PR_URL=<PR_URL или "нет">, PR_NUMBER=<… или "нет">, BASE_SHA=<BASE_SHA>, CYCLES_MAX=5.»
   Распарси блок ===STEP===: STATUS, VERDICT, CYCLES, PR_URL, PR_NUMBER, COMMIT, ISSUES.
   При ошибке/исключении step-runner — STATUS=error, ISSUES=«<что упало>».
4. Обнови STATE.steps[ШАГ] = {status, verdict, cycles, issues, base_sha, updated=<ISO>}. Запиши STATE на диск (json).
5. Если появился PR_URL/PR_NUMBER — обнови STATE.pr_url/pr_number, запиши.
6. ДАЛЬШЕ — следующий шаг. Без вопросов, без остановки, независимо от результата.

## Итог
После всех шагов:
- Если PR ещё не создан — создай: gh pr create --base master --head <BRANCH> --title "Pipeline: <SLUG>" --body "Шаги: <список>.".
- gh pr comment <PR> --body "Pipeline завершён. ✅done:<n>, ⚠️failed:<m>, ⛔error:<k>. Детали: .kilo/.pipeline-state.json".
- Сообщи: SLUG, BRANCH, PR_URL, таблицу шагов (файл / статус / вердикт / циклы).

## Жёсткие правила
- НИКАКИХ вопросов.
- НИКОГДА не останавливайся между шагами (успех/провал/ошибка — всё равно дальше).
- Один BRANCH и один PR на весь pipeline; коммиты накапливаются по шагам.
- Не мерджи PR.
- Мусор в STEPS_DIR игнорируй.
- STATE пиши после КАЖДОГО шага (переживёт рестарт ночью и доработает).
- .kilo/.pipeline-state.json НИКОГДА не коммить (локальное состояние).
- Предполагается чистый working tree на master перед запуском.
