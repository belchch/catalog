import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { ApplyMode, DocumentOut, SkillOut } from '../api.ts'
import type { UseSkillsResult } from '../hooks/useSkills.ts'
import { DocumentCombobox } from './DocumentCombobox.tsx'
import { CodeIcon, CommitIcon, PencilIcon, TrashIcon } from './icons.tsx'

interface SkillsPanelProps {
  skills: UseSkillsResult
  documents: DocumentOut[]
  defaultDocId: string | null
  onApply: (skillId: string, docIds: string[], mode: ApplyMode, prompt?: string) => void
  onEdit: (skillId: string, name: string) => void
  onDelete: (skillId: string) => void
  onRename: (skillId: string, name: string) => Promise<void>
}

type InputArity = 1 | 2 | null

type SkillTarget = {
  arity: InputArity
  slots: (string | null)[]
}

function skillArity(skill: SkillOut): InputArity {
  if (skill.input_arity === 1 || skill.input_arity === 2) return skill.input_arity
  return null
}

function defaultSlots(
  arity: InputArity,
  defaultDocId: string | null,
  validDocIds: Set<string>,
): (string | null)[] {
  if (arity === 1) {
    return defaultDocId && validDocIds.has(defaultDocId) ? [defaultDocId] : []
  }
  if (arity === 2) return [null, null]
  return []
}

function filterValidSlots(slots: (string | null)[], docIds: Set<string>): (string | null)[] {
  return slots.map((id) => (id != null && docIds.has(id) ? id : null))
}

function isSelectionValid(arity: InputArity, slots: (string | null)[]): boolean {
  if (arity === 1) return slots.length === 1 && slots[0] != null
  if (arity === 2) {
    return (
      slots.length === 2 &&
      slots[0] != null &&
      slots[1] != null &&
      slots[0] !== slots[1]
    )
  }
  return slots.filter((id): id is string => id != null).length >= 1
}

function nonempty(value: string | null | undefined): string | null {
  if (value == null) return null
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : null
}

function hasModelMeta(skill: SkillOut): boolean {
  return (
    nonempty(skill.provider) != null ||
    nonempty(skill.model) != null ||
    nonempty(skill.reasoning) != null
  )
}

function SkillModelMeta({ skill }: { skill: SkillOut }) {
  const provider = nonempty(skill.provider)
  const model = nonempty(skill.model)
  const reasoning = nonempty(skill.reasoning)
  if (provider == null && model == null && reasoning == null) return null
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px]">
      {provider != null && (
        <span className="inline-flex min-w-0 items-center gap-1">
          <span className="text-ink-faint">Провайдер</span>
          <span className="text-ink-muted">{provider}</span>
        </span>
      )}
      {model != null && (
        <span className="inline-flex min-w-0 items-center gap-1">
          <span className="text-ink-faint">Модель</span>
          <span className="max-w-[12rem] truncate text-ink-muted" title={model}>
            {model}
          </span>
        </span>
      )}
      {reasoning != null && (
        <span className="inline-flex min-w-0 items-center gap-1">
          <span className="text-ink-faint">Рассуждения</span>
          <span className="text-ink-muted">{reasoning}</span>
        </span>
      )}
    </div>
  )
}

function applyDocIds(arity: InputArity, slots: (string | null)[]): string[] {
  if (arity === 1) return slots[0] != null ? [slots[0]] : []
  if (arity === 2) {
    return slots[0] != null && slots[1] != null ? [slots[0], slots[1]] : []
  }
  return slots.filter((id): id is string => id != null)
}

function mode2Hint(slots: (string | null)[]): string | null {
  const a = slots[0] ?? null
  const b = slots[1] ?? null
  if (a == null || b == null) return 'Выберите два разных документа'
  if (a === b) return 'Документы должны отличаться'
  return null
}

function showsApplyPrompt(skill: SkillOut): boolean {
  if (skill.kind === 'script') return false
  if (skill.kind === 'agent') return true
  if (skill.tags.includes('ai')) return true
  if (skill.tags.includes('python')) return false
  return false
}

function applyPromptArg(draft: string | undefined): string | undefined {
  const trimmed = draft?.trim()
  return trimmed ? trimmed : undefined
}

function arityLabel(arity: InputArity): { symbol: string; title: string } {
  if (arity === 1) return { symbol: '1', title: 'Один документ' }
  if (arity === 2) return { symbol: '2', title: 'Два документа' }
  return { symbol: '∗', title: 'Несколько документов' }
}

function skillMatchesQuery(skill: SkillOut, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const haystack = [skill.name, skill.description ?? '', skill.tags.join(' ')]
    .join(' ')
    .toLowerCase()
  return haystack.includes(q)
}

const btnClass = 'btn-secondary text-[11px]'

export function SkillsPanel({
  skills,
  documents,
  defaultDocId,
  onApply,
  onEdit,
  onDelete,
  onRename,
}: SkillsPanelProps) {
  const [target, setTarget] = useState<Record<string, SkillTarget>>({})
  const [prompts, setPrompts] = useState<Record<string, string>>({})
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [descExpanded, setDescExpanded] = useState(false)
  const [renameId, setRenameId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [renameSaving, setRenameSaving] = useState(false)
  const renameSavingRef = useRef(false)
  const optionRefs = useRef<Record<string, HTMLDivElement | null>>({})
  const listRef = useRef<HTMLUListElement | null>(null)
  const renameTriggerRef = useRef<HTMLButtonElement | null>(null)
  const deleteBtnRef = useRef<HTMLButtonElement | null>(null)
  const focusRenameTriggerRef = useRef(false)
  const validDocIds = new Set(documents.map((d) => d.id))

  const filtered = useMemo(
    () => skills.skills.filter((s) => skillMatchesQuery(s, query)),
    [skills.skills, query],
  )

  const selected = useMemo(
    () => skills.skills.find((s) => s.id === selectedId) ?? null,
    [skills.skills, selectedId],
  )

  useEffect(() => {
    if (selectedId == null) return
    if (!skills.skills.some((s) => s.id === selectedId)) {
      setSelectedId(null)
      setConfirmOpen(false)
      setDescExpanded(false)
      return
    }
    if (!filtered.some((s) => s.id === selectedId)) {
      setSelectedId(null)
      setConfirmOpen(false)
      setDescExpanded(false)
    }
  }, [skills.skills, filtered, selectedId])

  useEffect(() => {
    setDescExpanded(false)
    setConfirmOpen(false)
  }, [selectedId])

  useEffect(() => {
    if (renameId != null || !focusRenameTriggerRef.current) return
    focusRenameTriggerRef.current = false
    renameTriggerRef.current?.focus()
  }, [renameId])

  useEffect(() => {
    if (selectedId == null) return
    const onMouseDown = (e: MouseEvent) => {
      if (renameSavingRef.current) return
      const list = listRef.current
      if (list != null && e.target instanceof Node && list.contains(e.target)) return
      renameSavingRef.current = false
      setRenameId(null)
      setRenameValue('')
      setRenameSaving(false)
      setConfirmOpen(false)
      setSelectedId(null)
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [selectedId])

  const slotsFor = (skill: SkillOut): (string | null)[] => {
    const arity = skillArity(skill)
    const stored = target[skill.id]
    if (stored && stored.arity === arity) {
      if (arity === 2) {
        const filteredSlots = filterValidSlots(
          [stored.slots[0] ?? null, stored.slots[1] ?? null],
          validDocIds,
        )
        return filteredSlots
      }
      return filterValidSlots(stored.slots, validDocIds).filter((id) => id != null)
    }
    return defaultSlots(arity, defaultDocId, validDocIds)
  }

  const setSlots = (skillId: string, arity: InputArity, slots: (string | null)[]) => {
    setTarget((prev) => ({ ...prev, [skillId]: { arity, slots } }))
  }

  const clearRename = () => {
    renameSavingRef.current = false
    setRenameId(null)
    setRenameValue('')
    setRenameSaving(false)
  }

  const startRename = (skill: SkillOut) => {
    setConfirmOpen(false)
    setRenameId(skill.id)
    setRenameValue(skill.name)
    renameSavingRef.current = false
    setRenameSaving(false)
  }

  const saveRename = async (skillId: string, currentName: string) => {
    const trimmed = renameValue.trim()
    if (!trimmed) return
    if (trimmed === currentName) {
      clearRename()
      return
    }
    renameSavingRef.current = true
    setRenameSaving(true)
    try {
      await onRename(skillId, trimmed)
      clearRename()
    } catch {
      renameSavingRef.current = false
      setRenameSaving(false)
    }
  }

  const selectSkill = (id: string) => {
    setSelectedId(id)
    clearRename()
    setConfirmOpen(false)
  }

  const escapeCascade = (): boolean => {
    if (confirmOpen) {
      setConfirmOpen(false)
      deleteBtnRef.current?.focus()
      return true
    }
    if (renameId != null) {
      focusRenameTriggerRef.current = true
      clearRename()
      return true
    }
    setSelectedId(null)
    return false
  }

  const moveSelection = (dir: 1 | -1) => {
    if (filtered.length === 0) return
    const idx = selectedId == null ? -1 : filtered.findIndex((s) => s.id === selectedId)
    let next: number
    if (idx < 0) {
      next = dir === 1 ? 0 : filtered.length - 1
    } else {
      next = Math.max(0, Math.min(filtered.length - 1, idx + dir))
    }
    const nextId = filtered[next]!.id
    setSelectedId(nextId)
    clearRename()
    setConfirmOpen(false)
    requestAnimationFrame(() => {
      optionRefs.current[nextId]?.scrollIntoView({ block: 'nearest' })
    })
  }

  const applyPersistSelected = () => {
    if (selected == null || selected.status !== 'committed') return
    const arity = skillArity(selected)
    const slots = slotsFor(selected)
    if (!isSelectionValid(arity, slots)) return
    const docIds = applyDocIds(arity, slots)
    onApply(selected.id, docIds, 'persist', applyPromptArg(prompts[selected.id]))
  }

  const onListKeyDown = (e: KeyboardEvent) => {
    if (e.target !== e.currentTarget) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      moveSelection(1)
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      moveSelection(-1)
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      applyPersistSelected()
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      escapeCascade()
    }
  }

  const onActionsEscape = (e: KeyboardEvent) => {
    if (e.key !== 'Escape' || e.defaultPrevented) return
    e.preventDefault()
    e.stopPropagation()
    const kept = escapeCascade()
    if (!kept) {
      listRef.current?.focus()
    }
  }

  const hasSkills = skills.skills.length > 0
  const renameEmpty = renameValue.trim().length === 0

  return (
    <div className="flex flex-col gap-2">
      {skills.error && <p className="text-xs text-danger-ink">{skills.error}</p>}

      {!hasSkills && (
        <p className="text-xs text-ink-faint">
          Скиллов пока нет — создайте из сессии планировщика.
        </p>
      )}

      {hasSkills && (
        <>
          <input
            type="search"
            className="field text-[11px]"
            placeholder="Поиск скиллов…"
            aria-label="Поиск скиллов"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />

          {filtered.length === 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs text-ink-faint">Ничего не найдено</p>
              <button
                type="button"
                className={btnClass}
                onClick={() => setQuery('')}
              >
                Сбросить
              </button>
            </div>
          ) : (
            <ul
              ref={listRef}
              role="listbox"
              aria-label="Скиллы"
              tabIndex={0}
              className="flex flex-col gap-0.5 rounded outline-none focus-visible:ring-2 focus-visible:ring-brand"
              onKeyDown={onListKeyDown}
            >
              {filtered.map((s) => {
                const isSelected = selectedId === s.id
                const arity = skillArity(s)
                const arityInfo = arityLabel(arity)
                const visibleTags = s.tags.slice(0, 2)
                const extraTags = s.tags.length - visibleTags.length
                const statusTitle = s.status === 'committed' ? 'committed' : 'draft'
                const slots = isSelected ? slotsFor(s) : []
                const valid = isSelected ? isSelectionValid(arity, slots) : false
                const docIds = isSelected ? applyDocIds(arity, slots) : []
                const hint = isSelected && arity === 2 ? mode2Hint(slots) : null
                const desc = s.description?.trim() ?? ''
                const descNeedsToggle = desc.length > 72
                const commitTitle =
                  s.status !== 'draft' ? 'Скил уже закоммичен' : 'Коммит'
                const showActionsRule =
                  desc.length > 0 || hasModelMeta(s)

                return (
                  <li key={s.id} className="min-w-0">
                    <div
                      ref={(el) => {
                        optionRefs.current[s.id] = el
                      }}
                      role="option"
                      aria-selected={isSelected}
                      aria-label={`${s.name}, ${statusTitle}`}
                      title={`${s.name} (${statusTitle})`}
                      className={
                        'flex h-8 cursor-pointer items-center gap-2 overflow-hidden whitespace-nowrap rounded border-l-2 px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand ' +
                        (isSelected
                          ? 'border-brand bg-brand-soft text-ink'
                          : 'border-transparent text-ink-muted hover:bg-surface-hover')
                      }
                      onClick={() => selectSkill(s.id)}
                    >
                      <span
                        className={
                          'inline-block h-2 w-2 shrink-0 rounded-full ' +
                          (s.status === 'committed' ? 'bg-success' : 'bg-warning')
                        }
                        title={statusTitle}
                        aria-hidden
                      />
                      <span
                        className="min-w-0 flex-1 truncate text-xs font-medium text-ink"
                        title={s.name}
                      >
                        {s.name}
                      </span>
                      <span className="flex shrink-0 items-center gap-1">
                        {visibleTags.map((tag) => (
                          <span
                            key={tag}
                            className={tag === 'python' ? 'badge-info' : 'badge-accent'}
                          >
                            {tag}
                          </span>
                        ))}
                        {extraTags > 0 && (
                          <span className="badge-neutral">+{extraTags}</span>
                        )}
                      </span>
                      <span
                        className="shrink-0 rounded px-1.5 py-0.5 text-[10px] text-ink-faint"
                        title={arityInfo.title}
                      >
                        {arityInfo.symbol}
                      </span>
                    </div>

                    {isSelected && (
                      <div className="mt-1.5 flex flex-col gap-1.5 border-t border-line px-2 pb-1 pt-1.5">
                        {desc && (
                          <div>
                            <p
                              className={
                                'text-[11px] text-ink-faint ' +
                                (descExpanded ? '' : 'line-clamp-2')
                              }
                            >
                              {desc}
                            </p>
                            {(descNeedsToggle || descExpanded) && (
                              <button
                                type="button"
                                className="mt-0.5 text-[11px] text-ink-faint hover:text-ink-muted"
                                onClick={(e) => {
                                  e.stopPropagation()
                                  setDescExpanded((v) => !v)
                                }}
                              >
                                {descExpanded ? 'свернуть' : 'ещё'}
                              </button>
                            )}
                          </div>
                        )}
                        <SkillModelMeta skill={s} />
                        <div
                          className={
                            'flex flex-col gap-1.5' +
                            (showActionsRule ? ' border-t border-line pt-1.5' : '')
                          }
                          onBlur={(e) => {
                            const container = e.currentTarget
                            requestAnimationFrame(() => {
                              if (!container.isConnected) return
                              const active = document.activeElement
                              if (container.contains(active)) return
                              setConfirmOpen(false)
                            })
                          }}
                          onKeyDown={onActionsEscape}
                        >
                          {renameId === s.id ? (
                            <div
                              className="flex min-w-0 flex-wrap items-center gap-1.5"
                              onBlur={(e) => {
                                const container = e.currentTarget
                                requestAnimationFrame(() => {
                                  if (renameSavingRef.current) return
                                  if (!container.contains(document.activeElement)) {
                                    clearRename()
                                  }
                                })
                              }}
                            >
                              <input
                                type="text"
                                className="field min-w-[8rem] flex-1"
                                value={renameValue}
                                aria-label="Имя скила"
                                autoFocus
                                disabled={renameSaving}
                                onChange={(e) => setRenameValue(e.target.value)}
                                onFocus={(e) => {
                                  const len = e.target.value.length
                                  e.target.setSelectionRange(len, len)
                                }}
                                onKeyDown={(e) => {
                                  if (e.key === 'Enter') {
                                    e.preventDefault()
                                    e.stopPropagation()
                                    void saveRename(s.id, s.name)
                                  } else if (e.key === 'Escape') {
                                    e.preventDefault()
                                    e.stopPropagation()
                                    focusRenameTriggerRef.current = true
                                    clearRename()
                                  }
                                }}
                              />
                              <button
                                type="button"
                                className="btn-primary text-[11px]"
                                aria-label="Сохранить"
                                disabled={renameSaving || renameEmpty}
                                onClick={() => void saveRename(s.id, s.name)}
                              >
                                {renameSaving ? '…' : 'Сохранить'}
                              </button>
                              <button
                                type="button"
                                className={btnClass}
                                aria-label="Отмена"
                                disabled={renameSaving}
                                onClick={() => {
                                  focusRenameTriggerRef.current = true
                                  clearRename()
                                }}
                              >
                                Отмена
                              </button>
                            </div>
                          ) : (
                            <>
                              <div className="flex items-center gap-1.5">
                                <button
                                  ref={renameTriggerRef}
                                  type="button"
                                  className="btn-icon-soft"
                                  aria-label="Переименовать"
                                  title="Переименовать"
                                  onClick={() => startRename(s)}
                                >
                                  <PencilIcon />
                                </button>
                                <button
                                  type="button"
                                  className="btn-icon-soft-brand"
                                  aria-label="Редактировать скил"
                                  title="Редактировать скил"
                                  onClick={() => {
                                    clearRename()
                                    onEdit(s.id, s.name)
                                  }}
                                >
                                  <CodeIcon />
                                </button>
                                <button
                                  type="button"
                                  className="btn-icon-soft-success"
                                  aria-label="Коммит"
                                  title={commitTitle}
                                  disabled={s.status !== 'draft'}
                                  onClick={() => void skills.commit(s.id)}
                                >
                                  <CommitIcon />
                                </button>
                                <button
                                  ref={deleteBtnRef}
                                  type="button"
                                  className="btn-icon-soft-danger ml-auto"
                                  aria-label="Удалить скил"
                                  title="Удалить скил"
                                  aria-expanded={confirmOpen}
                                  onClick={() => {
                                    clearRename()
                                    setConfirmOpen(true)
                                  }}
                                >
                                  <TrashIcon />
                                </button>
                              </div>
                              {confirmOpen && (
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <span className="text-[11px] text-ink-muted">
                                    Удалить скил &laquo;{s.name}&raquo;?
                                  </span>
                                  <button
                                    type="button"
                                    autoFocus
                                    className="btn-danger text-[11px]"
                                    aria-label="Удалить"
                                    onClick={() => {
                                      setConfirmOpen(false)
                                      onDelete(s.id)
                                    }}
                                  >
                                    Удалить
                                  </button>
                                  <button
                                    type="button"
                                    className={btnClass}
                                    aria-label="Отмена"
                                    onClick={() => {
                                      setConfirmOpen(false)
                                      deleteBtnRef.current?.focus()
                                    }}
                                  >
                                    Отмена
                                  </button>
                                </div>
                              )}
                            </>
                          )}
                        </div>
                        {s.status === 'committed' && (
                          <div className="relative flex w-full flex-col gap-1.5 border-t border-line pt-1.5">
                            {documents.length === 0 && (
                              <span className="text-[11px] text-ink-faint">нет документов</span>
                            )}
                            {documents.length > 0 && arity === 1 && (
                              <div>
                                <div className="mb-0.5 text-[11px] text-ink-faint">Документ</div>
                                <DocumentCombobox
                                  documents={documents}
                                  value={slots[0] ?? null}
                                  onChange={(id) => setSlots(s.id, 1, id != null ? [id] : [])}
                                  ariaLabel="Документ"
                                  placeholder="Выберите документ"
                                  placement="top"
                                />
                              </div>
                            )}
                            {documents.length > 0 && arity === 2 && (
                              <div className="flex flex-col gap-1.5">
                                <div>
                                  <div className="mb-0.5 text-[11px] text-ink-faint">Документ 1</div>
                                  <DocumentCombobox
                                    documents={documents}
                                    value={slots[0] ?? null}
                                    onChange={(id) =>
                                      setSlots(s.id, 2, [id, slots[1] ?? null])
                                    }
                                    ariaLabel="Документ 1"
                                    placeholder="Выберите документ"
                                    placement="top"
                                  />
                                </div>
                                <div>
                                  <div className="mb-0.5 text-[11px] text-ink-faint">Документ 2</div>
                                  <DocumentCombobox
                                    documents={documents}
                                    value={slots[1] ?? null}
                                    onChange={(id) =>
                                      setSlots(s.id, 2, [slots[0] ?? null, id])
                                    }
                                    ariaLabel="Документ 2"
                                    placeholder="Выберите документ"
                                    placement="top"
                                  />
                                </div>
                                {hint && !valid && (
                                  <p className="text-[10px] text-warning-ink">{hint}</p>
                                )}
                              </div>
                            )}
                            {documents.length > 0 && arity === null && (
                              <div>
                                <div className="mb-0.5 text-[11px] text-ink-faint">Документы</div>
                                <DocumentCombobox
                                  documents={documents}
                                  multiple
                                  values={slots.filter((id): id is string => id != null)}
                                  onChange={(ids) => setSlots(s.id, null, ids)}
                                  ariaLabel="Документы"
                                  placeholder="Выберите документы"
                                  placement="top"
                                />
                              </div>
                            )}
                            {showsApplyPrompt(s) && (
                              <div>
                                <label
                                  htmlFor={`skill-prompt-${s.id}`}
                                  className="mb-0.5 block text-[11px] text-ink-faint"
                                >
                                  Промпт
                                </label>
                                <textarea
                                  id={`skill-prompt-${s.id}`}
                                  rows={2}
                                  aria-label="Промпт"
                                  placeholder="Уточнение для этого запуска (необязательно)"
                                  value={prompts[s.id] ?? ''}
                                  onChange={(e) =>
                                    setPrompts((prev) => ({
                                      ...prev,
                                      [s.id]: e.target.value,
                                    }))
                                  }
                                  className="field max-h-28 resize-y text-[11px]"
                                />
                              </div>
                            )}
                            <div className="flex flex-wrap gap-1.5">
                              <button
                                type="button"
                                className="btn-primary text-[11px]"
                                disabled={!valid || documents.length === 0}
                                title="Результат сразу сохраняется в новый документ"
                                onClick={() =>
                                  valid &&
                                  onApply(
                                    s.id,
                                    docIds,
                                    'persist',
                                    applyPromptArg(prompts[s.id]),
                                  )
                                }
                              >
                                В док{docIds.length > 1 ? ` (${docIds.length})` : ''}
                              </button>
                              <button
                                type="button"
                                className="btn-secondary text-[11px]"
                                disabled={!valid || documents.length === 0}
                                title="Результат выводится на экран; документ можно сохранить отдельно"
                                onClick={() =>
                                  valid &&
                                  onApply(
                                    s.id,
                                    docIds,
                                    'preview',
                                    applyPromptArg(prompts[s.id]),
                                  )
                                }
                              >
                                На экран{docIds.length > 1 ? ` (${docIds.length})` : ''}
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </>
      )}
    </div>
  )
}
