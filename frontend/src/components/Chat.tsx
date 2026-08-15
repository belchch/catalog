import { useEffect, useRef, useState } from 'react'
import type { DocumentOut } from '../api.ts'
import type { PlannerMessage } from '../hooks/usePlannerSession.ts'
import { ChatMessage } from './ChatMessage.tsx'
import { DocumentCombobox } from './DocumentCombobox.tsx'

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
}: ChatProps) {
  const [input, setInput] = useState('')
  const [selectedDocIds, setSelectedDocIds] = useState<string[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (messages.length === 0) return
    const el = scrollRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
  }, [messages])

  useEffect(() => {
    setSelectedDocIds([])
  }, [sessionId])

  useEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [input])

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
  }

  const submit = () => {
    sendCurrent(input.trim())
  }

  const canSubmit = !streaming && (input.trim().length > 0 || selectedDocIds.length > 0)

  const visibleSuggestions = streaming
    ? []
    : messages.length === 0
      ? STARTER_SUGGESTIONS
      : suggestions

  const removeSelected = (id: string) => {
    if (streaming) return
    setSelectedDocIds((prev) => prev.filter((x) => x !== id))
  }

  return (
    <div className="catalog-chat flex h-full min-h-0 flex-col">
      {editingSkillName && (
        <div className="shrink-0 bg-brand-soft px-4 py-1.5 text-xs text-brand-ink">
          Редактирование: {editingSkillName}
        </div>
      )}
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
        <div className="catalog-composer">
        {sessionDocuments.length > 0 && (
          <section className="mb-2" aria-label="Документы в сессии">
            <h2 className="mb-1 text-[11px] uppercase tracking-wide text-ink-faint">
              Документы в сессии
            </h2>
            <p className="mb-1 text-[11px] text-ink-faint">
              Агент видит только эти документы
            </p>
            <ul className="flex flex-wrap gap-1.5" role="list" aria-live="polite">
              {sessionDocuments.map((d) => (
                <li key={d.id} role="listitem" className="chip">
                  <span className="badge-neutral">{d.kind}</span>
                  <span className="truncate">{d.title}</span>
                  <button
                    type="button"
                    className="ml-0.5 text-ink-faint hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:text-ink-faint"
                    aria-label={`Убрать ${d.title} из сессии`}
                    disabled={streaming}
                    onClick={() => onRemoveDocument?.(d.id)}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
        {selectedDocs.length > 0 && (
          <div className="mb-1.5 flex max-h-[5.625rem] flex-wrap items-center gap-1.5 overflow-y-auto overscroll-contain">
            {selectedDocs.map((d) => (
              <span key={d.id} className="chip-brand">
                <span className="badge-neutral">{d.kind}</span>
                <span className="truncate">{d.title}</span>
                <button
                  type="button"
                  className="ml-0.5 text-ink-faint hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:text-ink-faint"
                  aria-label={`Убрать ${d.title}`}
                  disabled={streaming}
                  onClick={() => removeSelected(d.id)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>
        )}
        <div className="mb-2 w-44 max-w-[12rem]">
          <DocumentCombobox
            multiple
            documents={documents}
            values={selectedDocIds}
            onChange={setSelectedDocIds}
            ariaLabel="Добавить документы в сессию"
            placeholder="+ документ"
            disabled={streaming}
            placement="top"
            triggerClassName="chip flex w-full justify-between text-left hover:border-line-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-faint"
          />
        </div>
        {visibleSuggestions.length > 0 && (
          <div
            className="mb-2 flex flex-wrap gap-2"
            role="group"
            aria-label="Быстрые ответы"
          >
            {visibleSuggestions.map((s) => (
              <button
                key={s}
                type="button"
                className="chip transition-colors hover:border-line-brand hover:bg-surface-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-ink-faint"
                onClick={() => sendCurrent(s)}
                disabled={streaming}
              >
                {s}
              </button>
            ))}
          </div>
        )}
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
        <button
          type="button"
          className="btn-secondary mt-2"
          onClick={onCreateSkill}
          disabled={buildingSkill || proposingTracks || messages.length === 0}
          aria-busy={buildingSkill || proposingTracks}
        >
          {proposingTracks
            ? 'Подбираю варианты…'
            : buildingSkill
              ? 'Собираю скилл…'
              : editingSkillName
                ? 'Сохранить изменения'
                : 'Создать скилл из сессии'}
        </button>
        {sessionId && (
          <div className="mt-1.5 text-[11px] text-ink-faint">
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
  )
}
