import { useEffect, useRef, useState } from 'react'
import type { DocumentOut, SkillOut } from '../api.ts'
import type { PlannerMessage } from '../hooks/usePlannerSession.ts'
import { ChatMessage } from './ChatMessage.tsx'
import { DocumentCombobox } from './DocumentCombobox.tsx'
import { ToolsPopover } from './ToolsPopover.tsx'

const STARTER_SUGGESTIONS = [
  'Изучи доступные документы',
  'Опиши задачу для скилла',
  'Какие документы уже есть?',
]

interface ChatProps {
  messages: PlannerMessage[]
  streaming: boolean
  cancelling: boolean
  closed: boolean
  reconnecting: boolean
  error: string | null
  suggestions: string[]
  documents: DocumentOut[]
  sessionDocuments: DocumentOut[]
  sessionId: string | null
  onSend: (text: string, docIds?: string[], docs?: DocumentOut[]) => void
  onCancel: () => void
  onReconnect: () => void
  onRemoveDocument?: (docId: string) => void
  onCreateSkill: () => void
  buildingSkill: boolean
  proposingTracks: boolean
  editingSkillName: string | null
  buildError: string | null
  buildErrorIsTimeout: boolean
  sessionTimeoutSeconds: number
  onOpenTimeoutModal: () => void
  onDismissBuildError: () => void
  attachedSkillCount?: number
  onOpenTools?: () => void
  toolsOpen?: boolean
  onCloseTools?: () => void
  availableSkills?: SkillOut[]
  attachedSkillIds?: string[]
  onToggleTool?: (skillId: string, enabled: boolean) => void
  toolsLoading?: boolean
}

function formatDocMeta(d: DocumentOut): string {
  const kind = (d.kind || 'file').toUpperCase()
  return kind
}

export function Chat({
  messages,
  streaming,
  cancelling,
  closed,
  reconnecting,
  error,
  suggestions,
  documents,
  sessionDocuments,
  sessionId,
  onSend,
  onCancel,
  onReconnect,
  onRemoveDocument,
  onCreateSkill,
  buildingSkill,
  proposingTracks,
  editingSkillName,
  buildError,
  buildErrorIsTimeout,
  sessionTimeoutSeconds,
  onOpenTimeoutModal,
  onDismissBuildError,
  attachedSkillCount = 0,
  onOpenTools,
  toolsOpen = false,
  onCloseTools,
  availableSkills = [],
  attachedSkillIds = [],
  onToggleTool,
  toolsLoading = false,
}: ChatProps) {
  const [input, setInput] = useState('')
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const [docPickerOpen, setDocPickerOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const docPickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (messages.length === 0) return
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages])

  useEffect(() => {
    setSelectedDocIds([])
    setDocPickerOpen(false)
  }, [sessionId])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input])

  useEffect(() => {
    if (!docPickerOpen) return
    const onPointer = (e: MouseEvent) => {
      if (!docPickerRef.current?.contains(e.target as Node)) {
        setDocPickerOpen(false)
      }
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setDocPickerOpen(false)
    }
    document.addEventListener('mousedown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [docPickerOpen])

  const sessionIds = new Set(sessionDocuments.map((d) => d.id))
  const pendingDocs = selectedDocIds
    .filter((id) => !sessionIds.has(id))
    .map((id) => documents.find((d) => d.id === id))
    .filter((d): d is DocumentOut => d != null)

  const attachmentDocs: Array<DocumentOut & { pending?: boolean }> = [
    ...sessionDocuments.map((d) => ({ ...d, pending: false as const })),
    ...pendingDocs.map((d) => ({ ...d, pending: true as const })),
  ]

  const selectedDocs = selectedDocIds
    .map((id) => documents.find((d) => d.id === id))
    .filter((d): d is DocumentOut => d != null)

  const sendCurrent = (text: string) => {
    if (streaming) return
    if (!text && selectedDocIds.length === 0) return
    onSend(
      text,
      selectedDocIds.length > 0 ? selectedDocIds : undefined,
      selectedDocs.length > 0 ? selectedDocs : undefined,
    )
    setInput('')
    setSelectedDocIds([])
    setDocPickerOpen(false)
  }

  const submit = () => {
    sendCurrent(input.trim())
  }

  const canSubmit = !streaming && (input.trim().length > 0 || selectedDocIds.length > 0)

  const visibleSuggestions = streaming
    ? []
    : messages.length === 0
      ? STARTER_SUGGESTIONS
      : suggestions.slice(0, 3)

  const removePending = (id: string) => {
    if (streaming) return
    setSelectedDocIds((prev) => prev.filter((x) => x !== id))
  }

  const removeAttachment = (d: DocumentOut & { pending?: boolean }) => {
    if (d.pending) {
      removePending(d.id)
      return
    }
    onRemoveDocument?.(d.id)
  }

  const createSkillLabel = proposingTracks
    ? 'Подбираю варианты…'
    : buildingSkill
      ? 'Собираю скилл…'
      : editingSkillName
        ? 'Сохранить изменения'
        : 'Создать скилл'

  return (
    <div className="catalog-chat flex h-full min-h-0 flex-col">
      <div className="catalog-chat__header shrink-0 border-b border-line px-4 py-2">
        <div className="catalog-chat__content flex items-center gap-2">
          {editingSkillName ? (
            <p className="min-w-0 flex-1 truncate text-xs text-brand-ink">
              Редактирование: {editingSkillName}
            </p>
          ) : (
            <p className="min-w-0 flex-1 truncate text-xs text-ink-faint">Чат планировщика</p>
          )}
          <button
            type="button"
            className="btn-secondary shrink-0"
            onClick={onCreateSkill}
            disabled={buildingSkill || proposingTracks || messages.length === 0}
            aria-busy={buildingSkill || proposingTracks}
          >
            {createSkillLabel}
          </button>
        </div>
      </div>
      <div
        ref={scrollRef}
        role="region"
        tabIndex={0}
        aria-label="История сообщений"
        className="catalog-chat__scroll min-h-0 flex-1 overflow-y-auto px-5 py-6 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
      >
        <div className="catalog-chat__content">
          {messages.length === 0 && (
            <p className="catalog-chat__empty mt-16 text-center text-sm text-ink-faint">
              Опишите задачу для документа — планировщик изучит документы и предложит скилл.
            </p>
          )}
          {messages.map((m, i) => (
            <ChatMessage
              key={i}
              message={m}
              onRepeat={(content) => onSend(content)}
              streaming={streaming}
              closed={closed}
            />
          ))}
          {streaming && (
            <div className="my-2 text-xs text-ink-faint">●●● планировщик думает…</div>
          )}
          {(closed || reconnecting) && (
            <div
              className="my-2 flex items-center gap-2 text-xs"
              role="status"
              aria-live="polite"
              aria-busy={reconnecting}
            >
              <span className="text-warning-ink">
                {reconnecting ? 'Переподключаю…' : 'Соединение закрыто'}
              </span>
              <button
                type="button"
                className="btn-secondary"
                onClick={onReconnect}
                disabled={reconnecting}
                aria-busy={reconnecting}
              >
                {reconnecting ? 'Переподключаю…' : 'Переподключить'}
              </button>
            </div>
          )}
          {error && <div className="my-2 text-xs text-danger-ink">Ошибка: {error}</div>}
        </div>
      </div>
      <div className="catalog-composer-area shrink-0 p-4">
        <div className="catalog-chat__content">
          {visibleSuggestions.length > 0 && (
            <div
              className="mb-2 flex gap-2 overflow-x-auto overscroll-contain pb-0.5"
              role="group"
              aria-label="Быстрые ответы"
            >
              {visibleSuggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="chip shrink-0 transition-colors hover:border-line-brand hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-faint"
                  onClick={() => sendCurrent(s)}
                  disabled={streaming}
                >
                  {s}
                </button>
              ))}
            </div>
          )}
          {attachmentDocs.length > 0 && (
            <ul
              className="catalog-attachments mb-0 flex gap-2 overflow-x-auto overscroll-contain rounded-t-card border border-b-0 border-line bg-surface-muted px-2.5 py-2"
              role="list"
              aria-label="Документы в сессии"
              aria-live="polite"
            >
              {attachmentDocs.map((d) => (
                <li
                  key={`${d.pending ? 'p' : 's'}-${d.id}`}
                  role="listitem"
                  className={
                    'flex min-w-[9.5rem] max-w-[12rem] shrink-0 items-start gap-2 rounded-lg border bg-surface px-2.5 py-2 ' +
                    (d.pending ? 'border-line-brand' : 'border-line')
                  }
                >
                  <span className="mt-0.5 text-ink-faint" aria-hidden="true">
                    ▦
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-ink">{d.title}</p>
                    <p className="truncate text-[11px] text-ink-faint">
                      {formatDocMeta(d)}
                      {d.pending ? ' · к отправке' : ''}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="shrink-0 text-ink-faint hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:text-ink-faint"
                    aria-label={`Убрать ${d.title}`}
                    disabled={streaming}
                    onClick={() => removeAttachment(d)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div
            className={
              'catalog-composer ' +
              (attachmentDocs.length > 0 ? 'catalog-composer--attached' : '')
            }
          >
            <div className="flex items-end gap-2">
              <textarea
                ref={textareaRef}
                rows={1}
                className="field max-h-40 flex-1 resize-none overflow-y-auto rounded-md px-3 py-2 text-sm"
                placeholder="Сообщение планировщику…"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key !== 'Enter') return
                  if (e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return
                  if (e.nativeEvent.isComposing || e.keyCode === 229) return
                  e.preventDefault()
                  submit()
                }}
                disabled={streaming}
              />
              {streaming ? (
                <button
                  type="button"
                  className="btn-icon-danger"
                  onClick={onCancel}
                  disabled={cancelling}
                  aria-label="Остановить генерацию"
                  title={cancelling ? 'Останавливаю…' : 'Остановить генерацию'}
                >
                  <span aria-hidden="true">■</span>
                </button>
              ) : (
                <button
                  type="button"
                  className="btn-icon-brand"
                  onClick={submit}
                  disabled={!canSubmit}
                  aria-label="Отправить"
                  title="Отправить"
                >
                  <span aria-hidden="true">↑</span>
                </button>
              )}
            </div>
            <div className="mt-2 flex items-center gap-1.5">
              <div className="relative" ref={docPickerRef}>
                <button
                  type="button"
                  className="btn-ghost inline-flex h-8 w-8 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover"
                  aria-label="Добавить документ"
                  aria-expanded={docPickerOpen}
                  disabled={streaming}
                  onClick={() => setDocPickerOpen((v) => !v)}
                >
                  <span aria-hidden="true">+</span>
                </button>
                {docPickerOpen && (
                  <div className="absolute bottom-full left-0 z-20 mb-2 w-64">
                    <DocumentCombobox
                      multiple
                      documents={documents}
                      values={selectedDocIds}
                      onChange={setSelectedDocIds}
                      ariaLabel="Добавить документы в сессию"
                      placeholder="Выбрать документы"
                      disabled={streaming}
                      placement="top"
                      triggerClassName="chip flex w-full justify-between text-left hover:border-line-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-faint"
                    />
                  </div>
                )}
              </div>
              <div className="relative">
                <button
                  type="button"
                  className="btn-ghost relative inline-flex h-8 w-8 items-center justify-center rounded-full text-ink-muted hover:bg-surface-hover disabled:cursor-not-allowed disabled:text-ink-faint"
                  aria-label={
                    attachedSkillCount > 0
                      ? `Инструменты, разрешено ${attachedSkillCount}`
                      : 'Инструменты'
                  }
                  aria-expanded={toolsOpen}
                  disabled={streaming || !sessionId}
                  onClick={onOpenTools}
                  title="Инструменты"
                >
                  <span aria-hidden="true">⚒</span>
                  {attachedSkillCount > 0 && (
                    <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-ink px-1 text-[10px] font-medium text-surface">
                      {attachedSkillCount}
                    </span>
                  )}
                </button>
                <ToolsPopover
                  open={toolsOpen}
                  onClose={() => onCloseTools?.()}
                  skills={availableSkills}
                  attachedIds={attachedSkillIds}
                  onToggle={(id, enabled) => onToggleTool?.(id, enabled)}
                  onCreateSkill={onCreateSkill}
                  loading={toolsLoading}
                />
              </div>
              {sessionId && (
                <div className="ml-auto text-[11px] text-ink-faint">
                  Timeout: {sessionTimeoutSeconds}s
                  {' · '}
                  <button
                    type="button"
                    className="text-ink-faint underline-offset-2 hover:text-ink-muted hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                    onClick={onOpenTimeoutModal}
                    aria-label={`Изменить таймаут LLM сессии, сейчас ${sessionTimeoutSeconds} секунд`}
                  >
                    изменить
                  </button>
                </div>
              )}
            </div>
            {buildError && (
              <div
                role="alert"
                aria-live="assertive"
                className="mt-2 rounded-md border border-danger-line bg-danger-soft px-3 py-2 text-xs text-danger-ink"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 flex-1 whitespace-pre-wrap break-words">{buildError}</p>
                  <button
                    type="button"
                    className="shrink-0 text-ink-faint hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                    onClick={onDismissBuildError}
                    aria-label="Скрыть ошибку"
                  >
                    ✕
                  </button>
                </div>
                {buildErrorIsTimeout && (
                  <button
                    type="button"
                    className="mt-1.5 text-xs text-brand-ink underline underline-offset-2 hover:text-[color:var(--brand-link-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
                    onClick={onOpenTimeoutModal}
                  >
                    Увеличить таймаут…
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
