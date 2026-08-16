import { useEffect, useMemo, useRef, useState } from 'react'
import type { SkillOut } from '../api.ts'
import { ChevronRightIcon } from './icons.tsx'

export interface ToolsPopoverProps {
  open: boolean
  onClose: () => void
  skills: SkillOut[]
  attachedIds: string[]
  pendingIds?: string[]
  onToggle: (skillId: string, enabled: boolean) => void
  onCreateSkill?: () => void
  createDisabled?: boolean
  onOpenSkillCard?: (skillId: string) => void
  loading?: boolean
  error?: string | null
  id?: string
}

function skillMatchesQuery(skill: SkillOut, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const name = skill.name.toLowerCase()
  const desc = (skill.description ?? '').toLowerCase()
  return name.includes(q) || desc.includes(q)
}

function costLine(skill: SkillOut): string {
  if (skill.kind === 'script') return 'script · без LLM'
  const n = skill.estimated_llm_calls
  if (n > 0) {
    const word = n === 1 ? 'вызова' : 'вызовов'
    return `${skill.kind} · до ${n} LLM-${word}`
  }
  return skill.kind
}

function SkillSwitch({
  name,
  enabled,
  disabled,
  hint,
  onToggle,
}: {
  name: string
  enabled: boolean
  disabled: boolean
  hint?: string
  onToggle: () => void
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={enabled}
      aria-label={enabled ? `Отключить ${name}` : `Включить ${name} как инструмент`}
      aria-description={hint}
      title={hint}
      disabled={disabled}
      onClick={onToggle}
      className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:opacity-100"
    >
      <span
        className={
          'flex h-5 w-9 items-center rounded-full transition-colors motion-reduce:transition-none ' +
          (enabled ? 'bg-brand' : 'bg-surface-muted') +
          (disabled ? ' cursor-not-allowed' : '')
        }
      >
        <span
          className={
            'h-4 w-4 rounded-full bg-surface shadow transition-transform motion-reduce:transition-none ' +
            (enabled ? 'translate-x-4' : 'translate-x-0.5')
          }
        />
      </span>
    </button>
  )
}

function SkillRow({
  skill,
  enabled,
  pending,
  onToggle,
  onOpenSkillCard,
}: {
  skill: SkillOut
  enabled: boolean
  pending: boolean
  onToggle: (skillId: string, enabled: boolean) => void
  onOpenSkillCard?: (skillId: string) => void
}) {
  const switchDisabled = pending
  const desc = skill.description?.trim() ?? ''
  const descText = desc || 'Без описания'
  return (
    <li
      className="flex items-start gap-2 px-3 py-2 hover:bg-surface-hover"
      aria-busy={pending || undefined}
    >
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-1">
          <span className="truncate text-xs text-ink" title={skill.name}>
            {skill.name}
          </span>
          {skill.tags.includes('python') && (
            <span className="badge-info shrink-0">python</span>
          )}
          {skill.tags.includes('ai') && (
            <span className="badge-accent shrink-0">ai</span>
          )}
        </div>
        <p className="truncate text-[11px] text-ink-faint" title={desc || undefined}>
          {descText}
        </p>
        <p className="text-[11px] text-ink-faint">{costLine(skill)}</p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {onOpenSkillCard && (
          <button
            type="button"
            className="btn-icon-ghost"
            aria-label={`Открыть карточку ${skill.name}`}
            onClick={() => onOpenSkillCard(skill.id)}
          >
            <ChevronRightIcon />
          </button>
        )}
        <SkillSwitch
          name={skill.name}
          enabled={enabled}
          disabled={switchDisabled}
          hint={pending ? 'Применяем…' : undefined}
          onToggle={() => onToggle(skill.id, !enabled)}
        />
      </div>
    </li>
  )
}

export function ToolsPopover({
  open,
  onClose,
  skills,
  attachedIds,
  pendingIds = [],
  onToggle,
  onCreateSkill,
  createDisabled,
  onOpenSkillCard,
  loading = false,
  error,
  id,
}: ToolsPopoverProps) {
  const [query, setQuery] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)
  const pendingSet = useMemo(() => new Set(pendingIds), [pendingIds])

  useEffect(() => {
    if (!open) {
      setQuery('')
      return
    }
    searchRef.current?.focus()
  }, [open])

  const attachedSet = useMemo(() => new Set(attachedIds), [attachedIds])

  const { attached, available } = useMemo(() => {
    const attachedRows = attachedIds
      .map((skillId) => skills.find((s) => s.id === skillId))
      .filter((s): s is SkillOut => s != null && skillMatchesQuery(s, query))
    const availableRows = skills.filter(
      (s) => !attachedSet.has(s.id) && skillMatchesQuery(s, query),
    )
    return { attached: attachedRows, available: availableRows }
  }, [attachedIds, attachedSet, query, skills])

  if (!open) return null

  const showHeaders = attached.length > 0 && available.length > 0
  const showEmptySkills = !loading && skills.length === 0
  const showNoResults =
    !loading && skills.length > 0 && attached.length === 0 && available.length === 0

  const handleCreate = () => {
    onClose()
    onCreateSkill?.()
  }

  const handleOpenCard = onOpenSkillCard
    ? (skillId: string) => {
        onClose()
        onOpenSkillCard(skillId)
      }
    : undefined

  const resetSearch = () => {
    setQuery('')
    searchRef.current?.focus()
  }

  return (
    <div
      id={id}
      role="dialog"
      aria-label="Инструменты сессии"
      className="absolute bottom-full left-0 z-30 mb-2 w-80 max-w-[calc(100vw-2rem)] overflow-hidden rounded-card border border-line bg-surface shadow-card"
    >
      <div className="border-b border-line px-3 py-2">
        <p className="text-xs font-medium text-ink">Инструменты</p>
        <p className="text-[11px] text-ink-faint">
          Планировщик может вызывать включённые скиллы
        </p>
        <input
          ref={searchRef}
          type="search"
          className="field mt-2 text-xs"
          placeholder="Поиск…"
          aria-label="Поиск инструментов"
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        {error ? (
          <div
            role="alert"
            className="mt-2 rounded border border-danger-line bg-danger-soft px-2 py-1 text-[11px] text-danger-ink"
          >
            {error}
          </div>
        ) : null}
      </div>
      <ul
        className="max-h-72 overflow-y-auto py-1"
        role="list"
        aria-busy={loading || undefined}
      >
        {loading && (
          <li className="px-3 py-2 text-xs text-ink-faint">Загрузка…</li>
        )}
        {showEmptySkills && (
          <li className="px-3 py-2 text-xs text-ink-faint">
            Скиллов пока нет — создайте из сессии планировщика
          </li>
        )}
        {showNoResults && (
          <li className="px-3 py-2">
            <p className="text-xs text-ink-faint">Ничего не найдено</p>
            <button
              type="button"
              className="btn-secondary mt-1 text-[11px]"
              onClick={resetSearch}
            >
              Сбросить
            </button>
          </li>
        )}
        {!loading && showHeaders && (
          <li className="px-3 pb-0.5 pt-1.5 text-[10px] uppercase tracking-wide text-ink-faint">
            Включены
          </li>
        )}
        {!loading &&
          attached.map((skill) => (
            <SkillRow
              key={skill.id}
              skill={skill}
              enabled
              pending={pendingSet.has(skill.id)}
              onToggle={onToggle}
              onOpenSkillCard={handleOpenCard}
            />
          ))}
        {!loading && showHeaders && (
          <li className="px-3 pb-0.5 pt-1.5 text-[10px] uppercase tracking-wide text-ink-faint">
            Доступны
          </li>
        )}
        {!loading &&
          available.map((skill) => (
            <SkillRow
              key={skill.id}
              skill={skill}
              enabled={false}
              pending={pendingSet.has(skill.id)}
              onToggle={onToggle}
              onOpenSkillCard={handleOpenCard}
            />
          ))}
      </ul>
      <div className="border-t border-line px-3 py-2">
        <button
          type="button"
          className="btn-secondary w-full"
          onClick={handleCreate}
          disabled={createDisabled || !onCreateSkill}
        >
          Создать скилл
        </button>
      </div>
    </div>
  )
}
