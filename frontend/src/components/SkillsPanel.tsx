import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import type { ApplyMode, DocumentOut, SkillOut } from '../api.ts'
import type { UseSkillsResult } from '../hooks/useSkills.ts'
import { DocumentCombobox } from './DocumentCombobox.tsx'

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

function SkillModelMeta({ skill }: { skill: SkillOut }) {
  const provider = nonempty(skill.provider)
  const model = nonempty(skill.model)
  const reasoning = nonempty(skill.reasoning)
  if (provider == null && model == null && reasoning == null) return null
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px]">
      {provider != null && (
        <span className="inline-flex min-w-0 items-center gap-1">
          <span className="text-slate-500">Провайдер</span>
          <span className="text-slate-300">{provider}</span>
        </span>
      )}
      {model != null && (
        <span className="inline-flex min-w-0 items-center gap-1">
          <span className="text-slate-500">Модель</span>
          <span className="max-w-[12rem] truncate text-slate-300" title={model}>
            {model}
          </span>
        </span>
      )}
      {reasoning != null && (
        <span className="inline-flex min-w-0 items-center gap-1">
          <span className="text-slate-500">Рассуждения</span>
          <span className="text-slate-300">{reasoning}</span>
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

const btnClass =
  'rounded px-2 py-1 text-[11px] bg-slate-700 text-slate-200 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-1 focus:ring-slate-600'

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
  const [overflowOpen, setOverflowOpen] = useState(false)
  const [descExpanded, setDescExpanded] = useState(false)
  const [renameId, setRenameId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')
  const [renameSaving, setRenameSaving] = useState(false)
  const renameSavingRef = useRef(false)
  const optionRefs = useRef<Record<string, HTMLDivElement | null>>({})
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
      setOverflowOpen(false)
      setDescExpanded(false)
      return
    }
    if (!filtered.some((s) => s.id === selectedId)) {
      setSelectedId(null)
      setConfirmOpen(false)
      setOverflowOpen(false)
      setDescExpanded(false)
    }
  }, [skills.skills, filtered, selectedId])

  useEffect(() => {
    setDescExpanded(false)
    setConfirmOpen(false)
    setOverflowOpen(false)
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
    setOverflowOpen(false)
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
    setSelectedId((prev) => (prev === id ? null : id))
    clearRename()
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
      if (confirmOpen) {
        setConfirmOpen(false)
        return
      }
      if (overflowOpen) {
        setOverflowOpen(false)
        return
      }
      if (renameId != null) {
        clearRename()
        return
      }
      setSelectedId(null)
    }
  }

  const hasSkills = skills.skills.length > 0
  const renameEmpty = renameValue.trim().length === 0
  const toolbarDisabled = selected == null
  const commitDisabled = selected == null || selected.status !== 'draft'

  return (
    <div className="flex flex-col gap-2">
      {skills.error && <p className="text-xs text-red-400">{skills.error}</p>}

      {!hasSkills && (
        <p className="text-xs text-slate-500">
          Скиллов пока нет — создайте из сессии планировщика.
        </p>
      )}

      {hasSkills && (
        <>
          <input
            type="search"
            className="w-full rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-100 placeholder:text-slate-500 outline-none focus:ring-1 focus:ring-slate-600"
            placeholder="Поиск скиллов…"
            aria-label="Поиск скиллов"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />

          {renameId != null && selected != null && renameId === selected.id ? (
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
                className="min-w-[8rem] flex-1 rounded bg-slate-800 px-2 py-1 text-xs text-slate-100 disabled:opacity-50 focus:outline-none focus:ring-1 focus:ring-slate-600"
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
                    void saveRename(selected.id, selected.name)
                  } else if (e.key === 'Escape') {
                    e.preventDefault()
                    clearRename()
                  }
                }}
              />
              <button
                type="button"
                className="rounded bg-indigo-600 px-2 py-1 text-[11px] text-white disabled:opacity-50 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                disabled={renameSaving || renameEmpty}
                onClick={() => void saveRename(selected.id, selected.name)}
              >
                {renameSaving ? '…' : 'Сохранить'}
              </button>
              <button
                type="button"
                className={btnClass}
                disabled={renameSaving}
                onClick={clearRename}
              >
                Отмена
              </button>
            </div>
          ) : (
            <div
              className="flex flex-col gap-1.5"
              onBlur={(e) => {
                const container = e.currentTarget
                requestAnimationFrame(() => {
                  if (!container.contains(document.activeElement)) {
                    setOverflowOpen(false)
                    setConfirmOpen(false)
                  }
                })
              }}
            >
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  className={btnClass}
                  disabled={toolbarDisabled}
                  onClick={() => selected && startRename(selected)}
                >
                  Переименовать
                </button>
                <button
                  type="button"
                  className={btnClass}
                  disabled={toolbarDisabled}
                  onClick={() => {
                    if (!selected) return
                    clearRename()
                    onEdit(selected.id, selected.name)
                  }}
                >
                  Редактировать
                </button>
                <button
                  type="button"
                  className={btnClass}
                  disabled={commitDisabled}
                  onClick={() => selected && void skills.commit(selected.id)}
                >
                  Коммит
                </button>
                <div className="relative ml-auto">
                  <button
                    type="button"
                    className={btnClass}
                    disabled={toolbarDisabled}
                    aria-label="Ещё действия"
                    aria-expanded={overflowOpen || confirmOpen}
                    onClick={() => {
                      if (toolbarDisabled) return
                      setConfirmOpen(false)
                      setOverflowOpen((o) => !o)
                    }}
                  >
                    ⋯
                  </button>
                  {overflowOpen && !confirmOpen && selected != null && (
                    <div className="absolute right-0 z-10 mt-1 min-w-[7rem] rounded border border-slate-700 bg-slate-900 py-1 shadow-lg">
                      <button
                        type="button"
                        className="block w-full px-3 py-1.5 text-left text-[11px] text-red-400 hover:bg-slate-800"
                        onClick={() => {
                          clearRename()
                          setOverflowOpen(false)
                          setConfirmOpen(true)
                        }}
                      >
                        Удалить
                      </button>
                    </div>
                  )}
                </div>
              </div>
              {confirmOpen && selected != null && (
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] text-slate-300">
                    Удалить скил &laquo;{selected.name}&raquo;?
                  </span>
                  <button
                    type="button"
                    autoFocus
                    className="rounded bg-red-600/80 px-2 py-1 text-[11px] text-white focus:outline-none focus:ring-1 focus:ring-red-500"
                    onClick={() => {
                      const id = selected.id
                      setConfirmOpen(false)
                      onDelete(id)
                    }}
                  >
                    Удалить
                  </button>
                  <button
                    type="button"
                    className={btnClass}
                    onClick={() => setConfirmOpen(false)}
                  >
                    Отмена
                  </button>
                </div>
              )}
            </div>
          )}

          {filtered.length === 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xs text-slate-500">Ничего не найдено</p>
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
              role="listbox"
              aria-label="Скиллы"
              tabIndex={0}
              className="flex flex-col gap-0.5 outline-none focus:ring-1 focus:ring-slate-600 rounded"
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
                        'flex h-8 cursor-pointer items-center gap-2 overflow-hidden whitespace-nowrap rounded px-2 py-1.5 text-xs ' +
                        (isSelected
                          ? 'bg-indigo-600/15 text-slate-200'
                          : 'text-slate-300 hover:bg-slate-800/70')
                      }
                      onClick={() => selectSkill(s.id)}
                    >
                      <span
                        className={
                          'inline-block h-2 w-2 shrink-0 rounded-full ' +
                          (s.status === 'committed' ? 'bg-emerald-400' : 'bg-amber-400')
                        }
                        title={statusTitle}
                        aria-hidden
                      />
                      <span
                        className="min-w-0 flex-1 truncate text-xs font-medium text-slate-200"
                        title={s.name}
                      >
                        {s.name}
                      </span>
                      <span className="flex shrink-0 items-center gap-1">
                        {visibleTags.map((tag) => (
                          <span
                            key={tag}
                            className={
                              'rounded px-1.5 py-0.5 text-[10px] uppercase ' +
                              (tag === 'python'
                                ? 'bg-sky-600/30 text-sky-300'
                                : 'bg-fuchsia-600/30 text-fuchsia-300')
                            }
                          >
                            {tag}
                          </span>
                        ))}
                        {extraTags > 0 && (
                          <span className="rounded px-1.5 py-0.5 text-[10px] uppercase text-slate-400">
                            +{extraTags}
                          </span>
                        )}
                      </span>
                      <span
                        className="shrink-0 rounded px-1.5 py-0.5 text-[10px] text-slate-400"
                        title={arityInfo.title}
                      >
                        {arityInfo.symbol}
                      </span>
                    </div>

                    {isSelected && (
                      <div className="mt-1.5 flex flex-col gap-1.5 border-t border-slate-800 pt-1.5 px-2 pb-1">
                        {desc && (
                          <div>
                            <p
                              className={
                                'text-[11px] text-slate-400 ' +
                                (descExpanded ? '' : 'line-clamp-2')
                              }
                            >
                              {desc}
                            </p>
                            {(descNeedsToggle || descExpanded) && (
                              <button
                                type="button"
                                className="mt-0.5 text-[11px] text-slate-500 hover:text-slate-300"
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
                        {s.status === 'committed' && (
                          <div className="relative flex w-full flex-col gap-1.5">
                            {documents.length === 0 && (
                              <span className="text-[11px] text-slate-500">нет документов</span>
                            )}
                            {documents.length > 0 && arity === 1 && (
                              <div>
                                <div className="mb-0.5 text-[11px] text-slate-400">Документ</div>
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
                                  <div className="mb-0.5 text-[11px] text-slate-400">Документ 1</div>
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
                                  <div className="mb-0.5 text-[11px] text-slate-400">Документ 2</div>
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
                                  <p className="text-[10px] text-amber-400">{hint}</p>
                                )}
                              </div>
                            )}
                            {documents.length > 0 && arity === null && (
                              <div>
                                <div className="mb-0.5 text-[11px] text-slate-400">Документы</div>
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
                                  className="mb-0.5 block text-[11px] text-slate-400"
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
                                  className="max-h-28 w-full resize-y rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-100 placeholder:text-slate-500 outline-none focus:ring-1 focus:ring-slate-600"
                                />
                              </div>
                            )}
                            <div className="flex flex-wrap gap-1.5">
                              <button
                                type="button"
                                className="rounded bg-indigo-600 px-2 py-1 text-[11px] text-white disabled:opacity-50 focus:outline-none focus:ring-1 focus:ring-indigo-500"
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
                                className="rounded bg-slate-700 px-2 py-1 text-[11px] text-slate-200 disabled:opacity-50 focus:outline-none focus:ring-1 focus:ring-slate-600"
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
