import { useState } from 'react'
import type { ApplyMode, DocumentOut, SkillOut } from '../api.ts'
import type { UseSkillsResult } from '../hooks/useSkills.ts'
import { DocumentCombobox } from './DocumentCombobox.tsx'

interface SkillsPanelProps {
  skills: UseSkillsResult
  documents: DocumentOut[]
  defaultDocId: string | null
  onApply: (skillId: string, docIds: string[], mode: ApplyMode) => void
  onEdit: (skillId: string, name: string) => void
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

export function SkillsPanel({ skills, documents, defaultDocId, onApply, onEdit }: SkillsPanelProps) {
  const [target, setTarget] = useState<Record<string, SkillTarget>>({})
  const validDocIds = new Set(documents.map((d) => d.id))

  const slotsFor = (skill: SkillOut): (string | null)[] => {
    const arity = skillArity(skill)
    const stored = target[skill.id]
    if (stored && stored.arity === arity) {
      if (arity === 2) {
        const filtered = filterValidSlots(
          [stored.slots[0] ?? null, stored.slots[1] ?? null],
          validDocIds,
        )
        return filtered
      }
      return filterValidSlots(stored.slots, validDocIds).filter((id) => id != null)
    }
    return defaultSlots(arity, defaultDocId, validDocIds)
  }

  const setSlots = (skillId: string, arity: InputArity, slots: (string | null)[]) => {
    setTarget((prev) => ({ ...prev, [skillId]: { arity, slots } }))
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-200">Скиллы</h2>
        <button
          className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 disabled:opacity-50"
          onClick={() => void skills.refresh()}
          disabled={skills.loading}
        >
          {skills.loading ? '…' : 'Обновить'}
        </button>
      </div>
      {skills.error && <p className="text-xs text-red-400">{skills.error}</p>}
      <ul className="flex flex-col gap-2">
        {skills.skills.map((s) => {
          const arity = skillArity(s)
          const slots = slotsFor(s)
          const valid = isSelectionValid(arity, slots)
          const docIds = applyDocIds(arity, slots)
          const hint = arity === 2 ? mode2Hint(slots) : null

          return (
            <li key={s.id} className="rounded-md border border-slate-800 bg-slate-900/60 p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs font-medium text-slate-200">{s.name}</span>
                <div className="flex items-center gap-1.5">
                  {s.tags.map((tag) => (
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
                  <span
                    className={
                      'rounded px-1.5 py-0.5 text-[10px] uppercase ' +
                      (s.status === 'committed'
                        ? 'bg-emerald-600/30 text-emerald-300'
                        : 'bg-amber-600/30 text-amber-300')
                    }
                  >
                    {s.status}
                  </span>
                </div>
              </div>
              {s.description && (
                <p className="mt-1 text-[11px] text-slate-400">{s.description}</p>
              )}
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                <button
                  className="rounded bg-slate-700 px-2 py-1 text-[11px] text-slate-200"
                  onClick={() => onEdit(s.id, s.name)}
                >
                  Редактировать
                </button>
                {s.status === 'draft' && (
                  <button
                    className="rounded bg-slate-700 px-2 py-1 text-[11px] text-slate-200"
                    onClick={() => void skills.commit(s.id)}
                  >
                    Коммит
                  </button>
                )}
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
                        />
                      </div>
                    )}
                    <div className="flex flex-wrap gap-1.5">
                      <button
                        className="rounded bg-indigo-600 px-2 py-1 text-[11px] text-white disabled:opacity-50"
                        disabled={!valid || documents.length === 0}
                        title="Результат сразу сохраняется в новый документ"
                        onClick={() => valid && onApply(s.id, docIds, 'persist')}
                      >
                        В док{docIds.length > 1 ? ` (${docIds.length})` : ''}
                      </button>
                      <button
                        className="rounded bg-slate-700 px-2 py-1 text-[11px] text-slate-200 disabled:opacity-50"
                        disabled={!valid || documents.length === 0}
                        title="Результат выводится на экран; документ можно сохранить отдельно"
                        onClick={() => valid && onApply(s.id, docIds, 'preview')}
                      >
                        На экран{docIds.length > 1 ? ` (${docIds.length})` : ''}
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </li>
          )
        })}
        {skills.skills.length === 0 && (
          <p className="text-xs text-slate-500">
            Скиллов пока нет — создайте из сессии планировщика.
          </p>
        )}
      </ul>
    </div>
  )
}
