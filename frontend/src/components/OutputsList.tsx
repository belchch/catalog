import { useEffect, useRef, type Ref } from 'react'
import {
  MAX_SKILL_OUTPUTS,
  type OutputDraft,
  type OutputRowError,
} from '../api.ts'

const ROW_CLS = 'rounded border border-line bg-surface-muted p-2'
const MOVE_DISABLED =
  'btn-ghost disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-faint'

interface OutputsListProps {
  value: OutputDraft[]
  onChange: (next: OutputDraft[]) => void
  disabled?: boolean
  rowErrors?: (OutputRowError | null)[]
  firstKeyRef?: Ref<HTMLInputElement>
}

function setRef(ref: Ref<HTMLInputElement> | undefined, el: HTMLInputElement | null) {
  if (!ref) return
  if (typeof ref === 'function') ref(el)
  else ref.current = el
}

export function OutputsList({
  value,
  onChange,
  disabled = false,
  rowErrors = [],
  firstKeyRef,
}: OutputsListProps) {
  const pendingFocus = useRef<number | null>(null)
  const keyRefs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    const idx = pendingFocus.current
    if (idx == null) return
    pendingFocus.current = null
    keyRefs.current[idx]?.focus()
  }, [value.length])

  const updateRow = (index: number, patch: Partial<OutputDraft>) => {
    onChange(value.map((row, i) => (i === index ? { ...row, ...patch } : row)))
  }

  const move = (index: number, dir: -1 | 1) => {
    const next = index + dir
    if (next < 0 || next >= value.length) return
    const copy = value.slice()
    const [row] = copy.splice(index, 1)
    copy.splice(next, 0, row)
    onChange(copy)
  }

  const remove = (index: number) => {
    onChange(value.filter((_, i) => i !== index))
  }

  const add = () => {
    if (value.length >= MAX_SKILL_OUTPUTS || disabled) return
    pendingFocus.current = value.length
    onChange([...value, { key: '', description: '', multiple: false }])
  }

  return (
    <div className="flex flex-col gap-2">
      {value.map((row, index) => {
        const err = rowErrors[index]
        const keyId = `outputs-key-${index}`
        const descId = `outputs-desc-${index}`
        const keyErrId = `outputs-key-error-${index}`
        const descErrId = `outputs-desc-error-${index}`
        const multiId = `outputs-multiple-${index}`
        const multiHintId = `outputs-multiple-hint-${index}`
        const multiErrId = `outputs-multiple-error-${index}`
        const label = row.key.trim() || String(index + 1)
        return (
          <div key={`${index}-${row.key}`} className={ROW_CLS}>
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex items-center gap-2">
                  {index === 0 && <span className="badge-neutral">основной</span>}
                  <label className="block min-w-0 flex-1 text-[11px] text-ink-faint">
                    ключ
                    <input
                      id={keyId}
                      ref={(el) => {
                        keyRefs.current[index] = el
                        if (index === 0) setRef(firstKeyRef, el)
                      }}
                      type="text"
                      className="field mt-1"
                      value={row.key}
                      disabled={disabled}
                      aria-invalid={Boolean(err?.key)}
                      aria-describedby={err?.key ? keyErrId : undefined}
                      onChange={(e) => updateRow(index, { key: e.target.value })}
                    />
                  </label>
                </div>
                <label className="block text-[11px] text-ink-faint">
                  описание
                  <input
                    id={descId}
                    type="text"
                    className="field mt-1"
                    value={row.description}
                    disabled={disabled}
                    aria-invalid={Boolean(err?.description)}
                    aria-describedby={err?.description ? descErrId : undefined}
                    onChange={(e) => updateRow(index, { description: e.target.value })}
                  />
                </label>
                <label
                  className={
                    'mt-1 flex items-start gap-1.5 text-[11px] text-ink-faint' +
                    (disabled ? ' cursor-not-allowed' : '')
                  }
                >
                  <input
                    id={multiId}
                    type="checkbox"
                    className="mt-0.5 h-3 w-3 shrink-0 accent-brand"
                    checked={row.multiple === true}
                    disabled={disabled}
                    aria-invalid={Boolean(err?.multiple)}
                    aria-describedby={
                      err?.multiple ? `${multiHintId} ${multiErrId}` : multiHintId
                    }
                    onChange={(e) => updateRow(index, { multiple: e.target.checked })}
                  />
                  несколько документов
                </label>
                <p id={multiHintId} className="ml-[1.125rem] text-[10px] text-ink-faint">
                  число документов определяется при прогоне
                </p>
                {err?.key && (
                  <p id={keyErrId} className="mt-1 text-[11px] text-danger-ink">
                    {err.key}
                  </p>
                )}
                {err?.description && (
                  <p id={descErrId} className="mt-1 text-[11px] text-danger-ink">
                    {err.description}
                  </p>
                )}
                {err?.multiple && (
                  <p id={multiErrId} className="mt-1 text-[11px] text-danger-ink">
                    {err.multiple}
                  </p>
                )}
              </div>
              <div className="flex shrink-0 flex-col gap-0.5">
                <button
                  type="button"
                  className={MOVE_DISABLED}
                  disabled={disabled || index === 0}
                  aria-label={`Поднять выход ${label}`}
                  onClick={() => move(index, -1)}
                >
                  ↑
                </button>
                <button
                  type="button"
                  className={MOVE_DISABLED}
                  disabled={disabled || index === value.length - 1}
                  aria-label={`Опустить выход ${label}`}
                  onClick={() => move(index, 1)}
                >
                  ↓
                </button>
                <button
                  type="button"
                  className={MOVE_DISABLED}
                  disabled={disabled}
                  aria-label={`Удалить выход ${label}`}
                  onClick={() => remove(index)}
                >
                  ✕
                </button>
              </div>
            </div>
          </div>
        )
      })}
      <button
        type="button"
        className="btn-secondary self-start disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-faint"
        disabled={disabled || value.length >= MAX_SKILL_OUTPUTS}
        title={value.length >= MAX_SKILL_OUTPUTS ? 'максимум 8 выходов' : undefined}
        onClick={add}
      >
        Добавить выход
      </button>
    </div>
  )
}
