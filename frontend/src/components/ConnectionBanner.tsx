interface ConnectionBannerProps {
  reconnecting: boolean
  interrupted: boolean
  onReconnect: () => void
}

export function ConnectionBanner({
  reconnecting,
  interrupted,
  onReconnect,
}: ConnectionBannerProps) {
  const title = reconnecting
    ? 'Переподключаю…'
    : interrupted
      ? 'Соединение потеряно — ответ прерван'
      : 'Соединение потеряно'
  const subtitle = reconnecting
    ? null
    : interrupted
      ? 'Часть ответа могла не сохраниться. Переподключитесь и повторите запрос.'
      : 'Отправка сообщений недоступна.'

  return (
    <div
      className="my-3 flex items-start justify-between gap-3 rounded-md border border-warning-line bg-warning-soft px-3 py-2 text-xs text-warning-ink"
      role="status"
      aria-live="polite"
      aria-busy={reconnecting}
    >
      <div>
        <p className="font-medium">{title}</p>
        {subtitle && (
          <p className="mt-0.5 text-[11px] text-warning-ink/80">{subtitle}</p>
        )}
      </div>
      <button
        type="button"
        className="btn-secondary shrink-0"
        onClick={onReconnect}
        disabled={reconnecting}
        aria-busy={reconnecting}
      >
        {reconnecting ? 'Переподключаю…' : 'Переподключить'}
      </button>
    </div>
  )
}
