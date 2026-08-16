import { useEffect, useId, useRef, useState } from 'react'
import type { DocumentOut, SkillOut } from '../api.ts'
import type { PlannerMessage } from '../hooks/usePlannerSession.ts'
import { ChatMessage } from './ChatMessage.tsx'
import { ConnectionBanner } from './ConnectionBanner.tsx'
import { DocumentCombobox } from './DocumentCombobox.tsx'
import { FileTextIcon, PlusIcon, WrenchIcon } from './icons.tsx'
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
  interrupted: boolean
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
  pendingToolIds?: string[]
  onToggleTool?: (skillId: string, enabled: boolean) => void
  toolsLoading?: boolean
  toolsError?: string | null
  onOpenSkillCard?: (skillId: string) => void
}

export function Chat({
  messages,
  streaming,
  cancelling,
  closed,
  reconnecting,
  interrupted,
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
  pendingToolIds = [],
  onToggleTool,
  toolsLoading = false,
  toolsError = null,
  onOpenSkillCard,
}: ChatProps) {
  const [input, setInput] = useState('')
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const [pickerEpoch, setPickerEpoch] = useState(0)
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const toolsRootRef = useRef<HTMLDivElement>(null)
  const toolsButtonRef = useRef<HTMLButtonElement>(null)
  const restoreComposerFocusRef = useRef(false)
  const toolsPopoverId = useId()
  const socketDown = closed || reconnecting
  const liveStreaming = streaming && !socketDown
  const showBanner = !error && socketDown
  const noConnectionTitle = 'Нет соединения — переподключитесь'

  useEffect(() => {
    if (messages.length === 0 && !showBanner) return
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages, showBanner])

  useEffect(() => {
    if (closed || reconnecting) return
    if (!restoreComposerFocusRef.current) return
    restoreComposerFocusRef.current = false
    const active = document.activeElement
    if (
      active &&
      active !== document.body &&
      active !== textareaRef.current &&
      (active instanceof HTMLInputElement ||
        active instanceof HTMLTextAreaElement ||
        active instanceof HTMLSelectElement)
    ) {
      return
    }
    textareaRef.current?.focus()
  }, [closed, reconnecting])

  useEffect(() => {
    setSelectedDocIds([])
    setPickerEpoch((n) => n + 1)
  }, [sessionId])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input])

  const closeTools = (restoreFocus: boolean) => {
    onCloseTools?.()
    if (restoreFocus) toolsButtonRef.current?.focus()
  }

  useEffect(() => {
    if (!toolsOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      e.preventDefault()
      onCloseTools?.()
      toolsButtonRef.current?.focus()
    }
    const onPointer = (e: MouseEvent) => {
      if (!toolsRootRef.current?.contains(e.target as Node)) {
        onCloseTools?.()
      }
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onPointer)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onPointer)
    }
  }, [toolsOpen, onCloseTools])

  useEffect(() => {
    if (liveStreaming && toolsOpen) onCloseTools?.()
  }, [liveStreaming, toolsOpen, onCloseTools])

  const selectedDocs = selectedDocIds
    .map((id) => documents.find((d) => d.id === id))
    .filter((d): d is DocumentOut => d != null)

  const sessionIds = new Set(sessionDocuments.map((d) => d.id))
  const pendingDocs = selectedDocIds
    .filter((id) => !sessionIds.has(id))
    .map((id) => documents.find((d) => d.id === id))
    .filter((d): d is DocumentOut => d != null)
  const attachmentDocs = [
    ...sessionDocuments.map((doc) => ({ doc, pending: false })),
    ...pendingDocs.map((doc) => ({ doc, pending: true })),
  ]

  const closePicker = () => setPickerEpoch((n) => n + 1)

  const handleReconnect = () => {
    restoreComposerFocusRef.current = true
    onReconnect()
  }

  const sendCurrent = (text: string) => {
    if (liveStreaming || socketDown) return
    if (!text && selectedDocIds.length === 0) return
    onSend(
      text,
      selectedDocIds.length ? selectedDocIds : undefined,
      selectedDocs.length ? selectedDocs : undefined,
    )
    setInput('')
    setSelectedDocIds([])
    closePicker()
  }

  const canSubmit =
    !liveStreaming &&
    !socketDown &&
    (input.trim().length > 0 || selectedDocIds.length > 0)

  const visibleSuggestions = liveStreaming
    ? []
    : messages.length === 0
      ? STARTER_SUGGESTIONS
      : suggestions

  const removeAttachment = (id: string, pending: boolean) => {
    if (liveStreaming) return
    setSelectedDocIds((prev) => prev.filter((x) => x !== id))
    if (!pending) onRemoveDocument?.(id)
  }

  const attachmentMeta = (kind: string, pending: boolean) => {
    const label = kind.trim() ? kind.toUpperCase() : 'FILE'
    return pending ? `${label} · к отправке` : label
  }

  const toolsLabel =
    attachedSkillCount > 0
      ? `Инструменты, включено ${attachedSkillCount}`
      : 'Инструменты'
  const toolsDisabled = liveStreaming || !sessionId
  const toolsTitle = liveStreaming
    ? 'Идёт генерация'
    : !sessionId
      ? 'Отправьте сообщение, чтобы начать сессию'
      : 'Инструменты'

  const skillBusy = buildingSkill || proposingTracks
  const skillLabel = proposingTracks
    ? 'Подбираю варианты…'
    : buildingSkill
      ? 'Собираю скилл…'
      : editingSkillName
        ? 'Сохранить изменения'
        : 'Создать скилл'

  return (
    <div className="catalog-chat flex h-full min-h-0 flex-col">
      <header className="catalog-chat__header shrink-0 border-b border-line px-4 py-2">
        <div className="catalog-chat__content flex items-center gap-2">
          <p
            className={
              'min-w-0 flex-1 truncate text-xs ' +
              (editingSkillName ? 'text-brand-ink' : 'text-ink-faint')
            }
          >
            {editingSkillName
              ? `Редактирование: ${editingSkillName}`
              : 'Чат планировщика'}
          </p>
          <button
            type="button"
            className="btn-secondary shrink-0"
            onClick={onCreateSkill}
            disabled={skillBusy || messages.length === 0}
            aria-busy={skillBusy}
          >
            {skillLabel}
          </button>
        </div>
      </header>
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
            streaming={liveStreaming}
            closed={socketDown}
          />
        ))}
        {liveStreaming && (
          <div className="my-2 text-xs text-ink-faint">●●● планировщик думает…</div>
        )}
        {showBanner && (
          <ConnectionBanner
            reconnecting={reconnecting}
            interrupted={interrupted}
            onReconnect={handleReconnect}
          />
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
                disabled={liveStreaming || socketDown}
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {attachmentDocs.length > 0 && (
          <ul
            role="list"
            aria-label="Документы в сессии"
            aria-live="polite"
            className="catalog-attachments flex gap-2 overflow-x-auto overscroll-contain rounded-t-card border border-b-0 border-line bg-surface-muted px-2.5 py-2"
          >
            {attachmentDocs.map(({ doc, pending }) => (
              <li
                key={doc.id}
                role="listitem"
                className={
                  'flex min-w-[9.5rem] max-w-[12rem] shrink-0 items-start gap-2 rounded-lg border bg-surface px-2.5 py-2 ' +
                  (pending ? 'border-line-brand' : 'border-line')
                }
              >
                <FileTextIcon className="mt-0.5 text-ink-faint" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium text-ink" title={doc.title}>
                    {doc.title}
                  </p>
                  <p className="truncate text-[11px] text-ink-faint">
                    {attachmentMeta(doc.kind, pending)}
                  </p>
                </div>
                <button
                  type="button"
                  className="shrink-0 text-ink-faint hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:text-ink-faint"
                  aria-label={`Убрать ${doc.title}`}
                  disabled={liveStreaming}
                  onClick={() => removeAttachment(doc.id, pending)}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
        <div
          className={
            'catalog-composer' +
            (attachmentDocs.length > 0 ? ' catalog-composer--attached' : '')
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
              sendCurrent(input.trim())
            }}
            disabled={liveStreaming}
          />
          {liveStreaming ? (
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
              onClick={() => sendCurrent(input.trim())}
              disabled={!canSubmit}
              aria-label="Отправить"
              title={socketDown ? noConnectionTitle : 'Отправить'}
              aria-description={socketDown ? noConnectionTitle : undefined}
            >
              <span aria-hidden="true">↑</span>
            </button>
          )}
        </div>
        <div className="mt-2 flex items-center gap-1.5">
          <DocumentCombobox
            key={`${sessionId ?? 'none'}-${pickerEpoch}`}
            multiple
            documents={documents}
            values={selectedDocIds}
            onChange={setSelectedDocIds}
            ariaLabel="Добавить документ"
            placeholder="+"
            disabled={liveStreaming}
            placement="top"
            listClassName="w-64"
            triggerContent={<PlusIcon />}
            triggerClassName="btn-icon-ghost"
          />
          <div className="relative" ref={toolsRootRef}>
            <button
              ref={toolsButtonRef}
              type="button"
              className="btn-icon-ghost relative"
              onClick={() => onOpenTools?.()}
              disabled={toolsDisabled}
              aria-label={toolsLabel}
              title={toolsTitle}
              aria-description={toolsDisabled ? toolsTitle : undefined}
              aria-haspopup="dialog"
              aria-expanded={toolsOpen}
              aria-controls={toolsPopoverId}
            >
              <WrenchIcon />
              {attachedSkillCount > 0 && (
                <span
                  className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand px-1 text-[10px] font-medium text-white"
                  aria-hidden
                >
                  {attachedSkillCount}
                </span>
              )}
            </button>
            <ToolsPopover
              id={toolsPopoverId}
              open={toolsOpen}
              onClose={() => closeTools(true)}
              skills={availableSkills}
              attachedIds={attachedSkillIds}
              pendingIds={pendingToolIds}
              onToggle={(skillId, enabled) => onToggleTool?.(skillId, enabled)}
              onCreateSkill={onCreateSkill}
              createDisabled={skillBusy || messages.length === 0}
              onOpenSkillCard={onOpenSkillCard}
              loading={toolsLoading}
              error={toolsError}
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
