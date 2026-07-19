import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { ModelOut } from '../api.ts'
import { sortAndFilterModels } from '../lib/models.ts'

type ModelComboboxProps = {
  models: ModelOut[]
  value: string
  onChange: (modelId: string) => void
  ariaLabel?: string
  disabled?: boolean
  triggerClassName?: string
}

export function ModelCombobox({
  models,
  value,
  onChange,
  ariaLabel = 'Модель',
  disabled = false,
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
        disabled={disabled}
        className={
          triggerClassName ??
          'flex w-full items-center justify-between rounded bg-slate-800 px-2 py-1 text-left text-xs text-slate-100 disabled:opacity-50'
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
            <span className="shrink-0 text-slate-400">🧠</span>
          )}
        </span>
        <span className="ml-1 shrink-0 text-slate-400">▾</span>
      </button>
      {open && (
        <div
          id={listId}
          role="listbox"
          className="absolute z-10 mt-1 max-h-48 w-full overflow-y-auto rounded border border-slate-700 bg-slate-900 shadow-xl"
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.preventDefault()
              close()
              rootRef.current?.querySelector('button')?.focus()
            }
          }}
        >
          <div className="sticky top-0 border-b border-slate-800 bg-slate-900 p-1">
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Поиск…"
              className="w-full rounded bg-slate-800 px-2 py-1 text-xs text-slate-100 placeholder:text-slate-500"
              autoFocus
            />
          </div>
          {options.length === 0 && (
            <div className="px-2 py-1 text-xs text-slate-500">нет совпадений</div>
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
                    ? 'bg-indigo-600/20 text-white'
                    : 'text-slate-300 hover:bg-slate-800')
                }
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onChange(m.id)
                  close()
                }}
              >
                <span className="truncate">{m.name}</span>
                {m.supports_reasoning && (
                  <span className="shrink-0 text-slate-400">🧠</span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
