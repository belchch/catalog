# CATALOG-23 — Кнопка реконнект чата

- **Задача Plane:** [CATALOG-23](https://app.plane.so/belchch/projects/catalog-app/work-items/23) (id: `0f4bbf4f-1360-45ba-9f80-ce8cf4fef5b5`, state: In Progress)
- **Статус плана:** Analyzed
- **Тип шага:** ui
- **Предпосылки:** желательно `CATALOG-23-code-ws-idle-timeout.md` (keepalive), но кнопка полезна и без него
- **Цель:** При «Соединение закрыто» — явная кнопка реконнекта; сброс ложного `closed` при живом сокете.

## Постановка задачи (актуальное ТЗ)
_(источник: последний комментарий от 2026-07-17)_

Стабильно каждые ~5 минут «Соединение закрыто». Увеличить таймаут и сделать кнопку реконнект.

## Предыстория

> Это уже было: старое описание и предыдущие обсуждения. Приведено для контекста, НЕ является актуальным заданием.

Описание + комментарий про investigate-first — см. code-план.

## Контекст

- Баннер: `Chat.tsx:90` («Соединение закрыто»).
- `usePlannerSession`: `closed` ставится в `onClose`; cleanup зовёт `conn.close()`; `setClosed(false)` только при смене `sessionId` — не при reconnect (`usePlannerSession.ts:109-142`).
- `useRunStream` сбрасывает `closed` в начале эффекта — паттерн для копирования.
- `ws.ts` — reconnect out of scope historically.

## Затрагиваемые файлы

- `frontend/src/hooks/usePlannerSession.ts` — `reconnect()`, сброс `closed` при open/effect.
- `frontend/src/components/Chat.tsx` — кнопка «Переподключить» рядом с баннером.
- При необходимости `ws.ts` — опции reconnect.

## План действий

1. Кнопка реконнект при `closed` → пересоздать WS для текущего `sessionId`, сбросить `closed`/`error`.
2. При успешном `onopen` всегда `setClosed(false)`.
3. Исправить StrictMode/cleanup race: не оставлять `closed=true` после намеренного close эффекта (флаг `intentionalClose` или сброс в начале эффекта, как в `useRunStream`).
4. Ручная проверка: оборвать сеть / дождаться idle → кнопка восстанавливает чат.

## Критерии приёмки (Definition of Done)

- [ ] При «Соединение закрыто» видна кнопка реконнект; клик восстанавливает WS.
- [ ] Ложный баннер после StrictMode remount не залипает.
- [ ] `pnpm run build/lint/typecheck` зелёные.
