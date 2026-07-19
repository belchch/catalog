import { useEffect, useId, useRef, useState } from 'react'
import type { DocumentOut } from '../api.ts'

type DocumentComboboxProps = {
  documents: DocumentOut[]
  ariaLabel: string
  placeholder: string
  disabled?: boolean
  triggerClassName?: string
  placement?: 'bottom' | 'top'
} & (
  | {
      multiple?: false
      value: string | null
      onChange: (id: string | null) => void
    }
  | {
      multiple: true
      values: string[]
      onChange: (ids: string[]) => void
    }
)

export function DocumentCombobox(props: DocumentComboboxProps) {
  const {
    documents,
    ariaLabel,
    placeholder,
    multiple = false,
    disabled = false,
    triggerClassName,
    placement = 'bottom',
  } = props
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

  const selectedIds = multiple
    ? props.multiple === true
      ? props.values
      : []
    : props.multiple !== true && props.value
      ? [props.value]
      : []
  const selectedSet = new Set(selectedIds)
  const selectedDoc =
    !multiple && props.multiple !== true && props.value
      ? documents.find((d) => d.id === props.value)
      : undefined

  const q = filter.trim().toLowerCase()
  const options = q
    ? documents.filter((d) => d.title.toLowerCase().includes(q))
    : documents

  const triggerLabel = multiple
    ? selectedIds.length > 0
      ? `${selectedIds.length} выбрано`
      : placeholder
    : selectedDoc
      ? selectedDoc.title
      : placeholder

  const close = () => {
    setOpen(false)
    setFilter('')
  }

  const toggleMulti = (docId: string) => {
    if (props.multiple !== true) return
    const next = selectedSet.has(docId)
      ? props.values.filter((id) => id !== docId)
      : [...props.values, docId]
    props.onChange(next)
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
          'flex w-full items-center justify-between rounded bg-slate-800 px-2 py-1 text-left text-[11px] text-slate-100 disabled:opacity-50'
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
        <span className={`truncate ${selectedIds.length === 0 ? 'text-slate-500' : ''}`}>
          {triggerLabel}
        </span>
        <span className="ml-1 text-slate-400">▾</span>
      </button>
      {open && (
        <div
          id={listId}
          role="listbox"
          aria-multiselectable={multiple || undefined}
          className={
            'absolute z-10 max-h-48 w-full overflow-y-auto rounded border border-slate-700 bg-slate-900 shadow-xl ' +
            (placement === 'top' ? 'bottom-full mb-1' : 'mt-1')
          }
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              e.preventDefault()
              close()
              rootRef.current?.querySelector('button')?.focus()
            }
          }}
        >
          <div className="border-b border-slate-800 p-1">
            <input
              type="search"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Поиск…"
              className="w-full rounded bg-slate-800 px-2 py-1 text-[11px] text-slate-100 placeholder:text-slate-500"
              autoFocus
            />
          </div>
          {options.length === 0 && (
            <div className="px-2 py-1 text-[11px] text-slate-500">нет совпадений</div>
          )}
          {options.map((d) => {
            const selected = selectedSet.has(d.id)
            if (multiple) {
              return (
                <label
                  key={d.id}
                  role="option"
                  aria-selected={selected}
                  className="flex cursor-pointer items-center gap-1.5 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800"
                  onMouseDown={(e) => e.preventDefault()}
                >
                  <input
                    type="checkbox"
                    className="h-3 w-3 accent-indigo-500"
                    checked={selected}
                    onChange={() => toggleMulti(d.id)}
                  />
                  <span className="truncate">{d.title}</span>
                </label>
              )
            }
            return (
              <div
                key={d.id}
                role="option"
                aria-selected={selected}
                className={
                  'flex cursor-pointer items-center gap-1.5 px-2 py-1 text-[11px] ' +
                  (selected
                    ? 'bg-indigo-600/20 text-white'
                    : 'text-slate-300 hover:bg-slate-800')
                }
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  if (props.multiple !== true) props.onChange(d.id)
                  close()
                }}
              >
                <span className="truncate">{d.title}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
