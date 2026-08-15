import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { ModelOut } from '../api.ts'
import { sortAndFilterModels } from '../lib/models.ts'

type ModelComboboxProps = {
  models: ModelOut[]
  value: string
  onChange: (modelId: string) => void
  ariaLabel?: string
  disabled?: boolean
  busy?: boolean
  triggerClassName?: string
}

export function ModelCombobox({
  models,
  value,
  onChange,
  ariaLabel = 'Модель',
  disabled = false,
  busy = false,
  triggerClassName,
}: ModelComboboxProps) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')
  const rootRef = useRef<HTMLDivElement>(null)
  const listId = useId()

  useEffect(() => {
    if (!open) return
    const onPointer = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false)
        setFilter('')
      }
    }
    document.addEventListener('mousedown', onPointer)
    return () => document.removeEventListener('mousedown', onPointer)
  }, [open])

  useEffect(() => {
    if (disabled) {
      setOpen(false)
      setFilter('')
    }
  }, [disabled])

  const modelsKey = useMemo(() => models.map((m) => m.id).join('\0'), [models])

  useEffect(() => {
    setOpen(false)
    setFilter('')
  }, [modelsKey])

  const options = useMemo(() => sortAndFilterModels(models, filter), [models, filter])
  const selectedModel = useMemo(() => models.find((m) => m.id === value), [models, value])
  const triggerLabel = selectedModel?.name || value

  const close = () => {
    setOpen(false)
    setFilter('')
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        aria-label={ariaLabel}
        aria-disabled={disabled || undefined}
        aria-busy={busy || undefined}
        disabled={disabled}
        className={
          triggerClassName ??
          'field flex w-full items-center justify-between text-left'
        }
        onClick={() => {
          if (disabled) return
          setOpen((v) => !v)
        }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            e.preventDefault()
            close()
          }
        }}
      >
        <span className="flex min-w-0 items-center gap-1.5">
          <span className="truncate">{triggerLabel}</span>
          {selectedModel?.supports_reasoning && (
            <span className="shrink-0 text-ink-faint">🧠</span>
          )}
        </span>
        <span className="ml-1 shrink-0 text-ink-faint">▾</span>
      </button>
      {open && (
        <div
          id={listId}
          role="listbox"
          className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded border border-line bg-surface shadow-card"
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.preventDefault()
              close()
              rootRef.current?.querySelector('button')?.focus({ preventScroll: true })
            }
          }}
        >
          <div className="sticky top-0 border-b border-line bg-surface p-1">
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Поиск…"
              className="field"
              autoFocus
            />
          </div>
          {options.length === 0 && (
            <div className="px-2 py-1 text-xs text-ink-faint">нет совпадений</div>
          )}
          {options.map((m) => {
            const selected = m.id === value
            return (
              <div
                key={m.id}
                role="option"
                aria-selected={selected}
                className={
                  'flex cursor-pointer items-center gap-1.5 px-2 py-1 text-xs ' +
                  (selected
                    ? 'bg-brand-soft text-ink'
                    : 'text-ink-muted hover:bg-surface-hover')
                }
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange(m.id)
                  close()
                }}
              >
                <span className="truncate">{m.name}</span>
                {m.supports_reasoning && (
                  <span className="shrink-0 text-ink-faint">🧠</span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
