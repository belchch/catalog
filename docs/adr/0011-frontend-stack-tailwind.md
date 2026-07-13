# ADR 0011: Фронтенд-стек — React (Vite) + TypeScript + Tailwind CSS

- **Date:** 2026-07-13
- **Status:** Accepted

## Context
Нужен UI-слой. React выбран ранее (opus chat). Требовалось зафиксировать типизацию и подход к стилям; заказчик предложил Tailwind.

## Decision
Фронтенд = **Vite + React + TypeScript + Tailwind CSS (v3, PostCSS)**.
- **Vite** — dev-сервер и сборка.
- **TypeScript** — типобезопасность.
- **Tailwind v3** (а не v4) — стабильность и устоявшаяся документация.
- Менеджер пакетов — **pnpm** (доступен в окружении; npm как fallback).

## Consequences
**Плюсы:** быстрый dev, utility-first согласованность, TS-безопасность, лёгкая портируемость статики.
**Минусы:** «шум» utility-классов в разметке; v3 требует `tailwind.config.js` + PostCSS (приемлемо).

## Alternatives considered
- **Svelte** — отклонён (заказчик выбрал React).
- **CSS-in-JS / plain CSS** — отклонён (медленнее на старте, менее консистентно).
- **Tailwind v4** — отложен (новее, меньше устоявшейся документации); миграция позже тривиальна.
