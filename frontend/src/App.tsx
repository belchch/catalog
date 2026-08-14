import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ApiError,
  buildSkill,
  createSession,
  extractApiDetail,
  getHealth,
  getSession,
  isBuildTimeoutError,
  proposeSkillTracks,
  saveRunResult,
  selectSkillTrack,
  startEditSession,
  updateSessionTimeout,
  type ApplyMode,
  type ArtifactType,
  type DocumentOut,
  type ScanReport,
  type SkillPreview,
  type SkillTrack,
} from './api.ts'
import { ArtifactsPanel } from './components/ArtifactsPanel.tsx'
import { ArtifactSummaryCard } from './components/ArtifactSummaryCard.tsx'
import { Chat } from './components/Chat.tsx'
import { CollapsibleSection } from './components/CollapsibleSection.tsx'
import { DocumentList } from './components/DocumentList.tsx'
import { ModelSelector } from './components/ModelSelector.tsx'
import { SettingsIcon } from './components/icons.tsx'
import { SettingsPanel } from './components/SettingsPanel.tsx'
import { RescanReportModal } from './components/RescanReportModal.tsx'
import { RunView } from './components/RunView.tsx'
import { SessionsPanel } from './components/SessionsPanel.tsx'
import { SessionTimeoutModal } from './components/SessionTimeoutModal.tsx'
import { SkillSettingsModal } from './components/SkillSettingsModal.tsx'
import { SkillTrackPicker } from './components/SkillTrackPicker.tsx'
import { SkillsPanel } from './components/SkillsPanel.tsx'
import { SetupKeyScreen } from './components/SetupKeyScreen.tsx'
import { WorkspaceBar } from './components/WorkspaceBar.tsx'
import { WorkspacePicker } from './components/WorkspacePicker.tsx'
import { useDocuments } from './hooks/useDocuments.ts'
import { usePlannerSession } from './hooks/usePlannerSession.ts'
import { useRunStream } from './hooks/useRunStream.ts'
import { useSessions } from './hooks/useSessions.ts'
import { useSettings } from './hooks/useSettings.ts'
import { useSetup } from './hooks/useSetup.ts'
import { useSkills } from './hooks/useSkills.ts'
import { useWorkspace } from './hooks/useWorkspace.ts'

const SESSION_STORAGE_KEY = 'catalog.sessionId'

type MainPane = 'chat' | 'draft'
type DraftPane = 'summary' | 'editor'

function readStoredSessionId(): string | null {
  try {
    return localStorage.getItem(SESSION_STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStoredSessionId(id: string | null): void {
  try {
    if (id) localStorage.setItem(SESSION_STORAGE_KEY, id)
    else localStorage.removeItem(SESSION_STORAGE_KEY)
  } catch {}
}

const DEFAULT_SESSION_TIMEOUT = 60

function highlightFromDetail(detail: string): ArtifactType | null {
  const d = detail.toLowerCase()
  if (d.includes('meta')) return 'meta'
  if (d.includes('prompt')) return 'prompt'
  if (d.includes('script')) return 'script'
  return null
}

function useIsLg(): boolean {
  const [isLg, setIsLg] = useState(() =>
    typeof window !== 'undefined'
      ? window.matchMedia('(min-width: 1024px)').matches
      : true,
  )
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)')
    const onChange = () => setIsLg(mq.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])
  return isLg
}

export default function App() {
  const setup = useSetup()
  const workspace = useWorkspace()
  const hasWorkspace = Boolean(workspace.current)
  const docs = useDocuments(hasWorkspace)
  const skillsHook = useSkills(hasWorkspace)
  const settingsHook = useSettings(setup.keysConfigured)
  const sessions = useSessions(hasWorkspace)
  const isLg = useIsLg()

  const [sessionId, setSessionId] = useState<string | null>(() => readStoredSessionId())
  const [currentDocId, setCurrentDocId] = useState<string | null>(null)
  const [buildingSkill, setBuildingSkill] = useState(false)
  const [proposingTracks, setProposingTracks] = useState(false)
  const [trackChoice, setTrackChoice] = useState<SkillTrack[] | null>(null)
  const [buildError, setBuildError] = useState<string | null>(null)
  const [buildErrorIsTimeout, setBuildErrorIsTimeout] = useState(false)
  const [timeoutModalOpen, setTimeoutModalOpen] = useState(false)
  const [sessionTimeoutSeconds, setSessionTimeoutSeconds] = useState(DEFAULT_SESSION_TIMEOUT)
  const [notice, setNotice] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [settingsSkill, setSettingsSkill] = useState<{ skillId: string; preview: SkillPreview } | null>(null)
  const [editingSkill, setEditingSkill] = useState<{ skillId: string; name: string } | null>(null)
  const [savedResultDoc, setSavedResultDoc] = useState<DocumentOut | null>(null)
  const [savingResult, setSavingResult] = useState(false)
  const [openSessions, setOpenSessions] = useState(false)
  const [openDocs, setOpenDocs] = useState(false)
  const [openSkills, setOpenSkills] = useState(false)
  const [mainPane, setMainPane] = useState<MainPane>('chat')
  const [draftPane, setDraftPane] = useState<DraftPane>('summary')
  const [artifactHighlight, setArtifactHighlight] = useState<ArtifactType | null>(null)
  const [gitSha, setGitSha] = useState('')
  const [pickerOpen, setPickerOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [rescanning, setRescanning] = useState(false)
  const [rescanReport, setRescanReport] = useState<ScanReport | null>(null)
  const workspacePathRef = useRef<string | null>(null)
  const settingsButtonRef = useRef<HTMLButtonElement>(null)

  const handleSessionInvalid = useCallback(() => {
    writeStoredSessionId(null)
    setSessionId(null)
    setEditingSkill(null)
    setArtifactHighlight(null)
  }, [])

  const handleSettingsClose = useCallback(() => {
    setSettingsOpen(false)
    settingsButtonRef.current?.focus()
  }, [])

  const refreshSetup = setup.refresh
  const refreshProviders = settingsHook.refreshProviders

  const handleSettingsRefresh = useCallback(async () => {
    await refreshSetup()
    await refreshProviders()
  }, [refreshSetup, refreshProviders])

  const planner = usePlannerSession(hasWorkspace ? sessionId : null, {
    onSessionInvalid: handleSessionInvalid,
  })
  const { refreshSessionDocuments } = planner
  const run = useRunStream(activeRunId)
  const docsRefresh = docs.refresh
  const sessionsRefresh = sessions.refresh
  const skillsRefresh = skillsHook.refresh
  const workspaceRefreshCurrent = workspace.refreshCurrent
  const workspaceRefreshRecents = workspace.refreshRecents
  const workspaceRefreshBlocked = workspace.refreshBlocked
  const workspaceRescan = workspace.rescan

  useEffect(() => {
    writeStoredSessionId(sessionId)
  }, [sessionId])

  useEffect(() => {
    const nextPath = workspace.current?.path ?? null
    const prevPath = workspacePathRef.current
    if (prevPath !== null && nextPath !== prevPath) {
      setSessionId(null)
      setActiveRunId(null)
      setEditingSkill(null)
      setCurrentDocId(null)
      setSavedResultDoc(null)
      setBuildError(null)
      setArtifactHighlight(null)
    }
    workspacePathRef.current = nextPath
  }, [workspace.current?.path])

  const openPicker = useCallback(() => {
    setNotice(null)
    setPickerOpen(true)
    void workspaceRefreshBlocked()
  }, [workspaceRefreshBlocked])

  const handleWorkspaceOpened = useCallback(() => {
    setPickerOpen(false)
    setNotice(null)
    void workspaceRefreshCurrent()
    void workspaceRefreshRecents()
    void docsRefresh()
    void sessionsRefresh()
    void skillsRefresh()
  }, [
    workspaceRefreshCurrent,
    workspaceRefreshRecents,
    docsRefresh,
    sessionsRefresh,
    skillsRefresh,
  ])

  const handleBusyConflict = useCallback((detail: string) => {
    setNotice(detail)
    void workspaceRefreshBlocked()
  }, [workspaceRefreshBlocked])

  const handleRescan = useCallback(async () => {
    if (!hasWorkspace || rescanning) return
    setRescanning(true)
    setNotice(null)
    try {
      const report = await workspaceRescan()
      setRescanReport(report)
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setNotice(e.detail)
      } else {
        setNotice(extractApiDetail(e))
      }
    } finally {
      setRescanning(false)
    }
  }, [hasWorkspace, rescanning, workspaceRescan])

  const handleRescanClose = useCallback(() => {
    setRescanReport(null)
    void docsRefresh()
  }, [docsRefresh])

  useEffect(() => {
    void getHealth()
      .then((h) => {
        const sha = (h.git_sha || '').trim()
        if (sha && sha !== 'unknown') setGitSha(sha)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    setArtifactHighlight(null)
    setMainPane('chat')
    setDraftPane('summary')
    setBuildError(null)
    setBuildErrorIsTimeout(false)
    setTimeoutModalOpen(false)
  }, [sessionId])

  useEffect(() => {
    if (!sessionId || !hasWorkspace) {
      setSessionTimeoutSeconds(DEFAULT_SESSION_TIMEOUT)
      return
    }
    const fromList = sessions.sessions.find((s) => s.id === sessionId)
    if (fromList?.llm_timeout_seconds != null) {
      setSessionTimeoutSeconds(fromList.llm_timeout_seconds)
      return
    }
    let cancelled = false
    void getSession(sessionId)
      .then((s) => {
        if (!cancelled) setSessionTimeoutSeconds(s.llm_timeout_seconds)
      })
      .catch(() => {
        if (!cancelled) setSessionTimeoutSeconds(DEFAULT_SESSION_TIMEOUT)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, hasWorkspace, sessions.sessions])

  const handledRunFinishRef = useRef<string | null>(null)
  useEffect(() => {
    if (!run.finished || !activeRunId) return
    if (handledRunFinishRef.current === activeRunId) return
    handledRunFinishRef.current = activeRunId
    if (run.status === 'ok' && run.outputDocId) {
      void docsRefresh()
    }
    void refreshSessionDocuments()
    void workspaceRefreshBlocked()
  }, [run.finished, run.status, run.outputDocId, activeRunId, docsRefresh, refreshSessionDocuments, workspaceRefreshBlocked])

  const wasStreamingRef = useRef(false)
  useEffect(() => {
    if (wasStreamingRef.current && !planner.streaming) {
      void sessionsRefresh()
      void workspaceRefreshBlocked()
    }
    wasStreamingRef.current = planner.streaming
  }, [planner.streaming, sessionsRefresh, workspaceRefreshBlocked])

  const ensureSession = useCallback(async (): Promise<string> => {
    if (!hasWorkspace) throw new Error('Сначала откройте папку воркспейса')
    if (sessionId) return sessionId
    const created = await createSession()
    setSessionId(created.id)
    void sessions.refresh()
    return created.id
  }, [hasWorkspace, sessionId, sessions])

  const handleSend = useCallback(
    async (text: string, docIds?: string[]) => {
      try {
        await ensureSession()
        planner.send(text, docIds)
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e))
      }
    },
    [ensureSession, planner],
  )

  const handleSelectSession = useCallback(
    (id: string) => {
      if (id === sessionId) return
      setActiveRunId(null)
      setEditingSkill(null)
      setSessionId(id)
    },
    [sessionId],
  )

  const handleNewChat = useCallback(() => {
    setActiveRunId(null)
    setEditingSkill(null)
    setSessionId(null)
  }, [])

  const handleDeleteSession = useCallback(
    async (id: string) => {
      setNotice(null)
      try {
        await sessions.remove(id)
        if (id === sessionId) {
          setActiveRunId(null)
          setEditingSkill(null)
          setSessionId(null)
        }
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e))
      }
    },
    [sessions, sessionId],
  )

  const handleEditSkill = useCallback(async (skillId: string, name: string) => {
    setNotice(null)
    try {
      const started = await startEditSession(skillId)
      setActiveRunId(null)
      setSessionId(started.session_id)
      setEditingSkill({ skillId: started.skill_id, name })
      void sessions.refresh()
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    }
  }, [sessions])

  const handleDeleteSkill = useCallback(
    async (skillId: string) => {
      try {
        await skillsHook.remove(skillId)
        if (editingSkill?.skillId === skillId) {
          setEditingSkill(null)
          setSessionId(null)
        }
      } catch {}
    },
    [skillsHook, editingSkill],
  )

  const runBuildSkill = useCallback(async (sid: string) => {
    setBuildingSkill(true)
    setNotice(null)
    setBuildError(null)
    setBuildErrorIsTimeout(false)
    setArtifactHighlight(null)
    try {
      const built = await buildSkill(sid)
      setSettingsSkill({ skillId: built.skill_id, preview: built.config })
    } catch (e) {
      const detail = extractApiDetail(e)
      const timedOut = isBuildTimeoutError(e, detail)
      setBuildError(detail)
      setBuildErrorIsTimeout(timedOut)
      if (timedOut) setTimeoutModalOpen(true)
      const highlight = highlightFromDetail(detail)
      if (highlight) setArtifactHighlight(highlight)
      if (!window.matchMedia('(min-width: 1024px)').matches) {
        setMainPane('draft')
      }
    } finally {
      setBuildingSkill(false)
    }
  }, [])

  const handleCreateSkill = useCallback(async () => {
    if (!sessionId || buildingSkill || proposingTracks || trackChoice) return

    if (editingSkill != null) {
      await runBuildSkill(sessionId)
      return
    }

    setProposingTracks(true)
    setNotice(null)
    setBuildError(null)
    setBuildErrorIsTimeout(false)
    setArtifactHighlight(null)
    let proposed: Awaited<ReturnType<typeof proposeSkillTracks>> | null = null
    try {
      proposed = await proposeSkillTracks(sessionId)
    } catch {
      proposed = null
    }

    if (
      !proposed ||
      proposed.skipped ||
      proposed.fallback ||
      proposed.tracks.length === 0
    ) {
      setProposingTracks(false)
      await runBuildSkill(sessionId)
      return
    }

    if (proposed.tracks.length === 1) {
      try {
        await selectSkillTrack(sessionId, proposed.tracks[0])
      } catch (e) {
        setBuildError(extractApiDetail(e))
        setBuildErrorIsTimeout(false)
        return
      } finally {
        setProposingTracks(false)
      }
      await runBuildSkill(sessionId)
      return
    }

    setProposingTracks(false)
    setTrackChoice(proposed.tracks)
  }, [
    sessionId,
    buildingSkill,
    proposingTracks,
    trackChoice,
    editingSkill,
    runBuildSkill,
  ])

  const handleTrackSelect = useCallback(
    async (track: SkillTrack) => {
      if (!sessionId) return
      try {
        await selectSkillTrack(sessionId, track)
        await runBuildSkill(sessionId)
      } catch (e) {
        setBuildError(extractApiDetail(e))
        setBuildErrorIsTimeout(false)
      } finally {
        setTrackChoice(null)
      }
    },
    [sessionId, runBuildSkill],
  )

  const handleTrackCancel = useCallback(() => {
    setTrackChoice(null)
  }, [])

  const handleSaveSessionTimeout = useCallback(
    async (seconds: number) => {
      if (!sessionId) return
      const updated = await updateSessionTimeout(sessionId, seconds)
      setSessionTimeoutSeconds(updated.llm_timeout_seconds)
      sessions.patchLocal(updated)
    },
    [sessionId, sessions],
  )

  const handleSkillConfigured = useCallback(async () => {
    await skillsHook.refresh()
    setNotice('Скилл настроен (draft). Сделайте коммит, затем примените к документу.')
  }, [skillsHook])

  const handleApply = useCallback(
    async (skillId: string, docIds: string[], mode: ApplyMode, prompt?: string) => {
      setNotice(null)
      setSavedResultDoc(null)
      try {
        const sid = await ensureSession()
        const runId = await skillsHook.apply(skillId, docIds, mode, sid, prompt)
        setActiveRunId(runId)
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e))
      }
    },
    [skillsHook, ensureSession],
  )

  const handleSaveResult = useCallback(
    async (runId: string) => {
      setSavingResult(true)
      setNotice(null)
      try {
        const doc = await saveRunResult(runId)
        setSavedResultDoc(doc)
        await docs.refresh()
        await refreshSessionDocuments()
        setCurrentDocId(doc.id)
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e))
      } finally {
        setSavingResult(false)
      }
    },
    [docs, refreshSessionDocuments],
  )

  const showChat = isLg || mainPane === 'chat'
  const showDraft = isLg || mainPane === 'draft'

  if (setup.status === 'unknown') {
    return (
      <div className="flex h-screen items-center justify-center bg-surface">
        <p role="status" aria-live="polite" className="text-ink-faint">
          Загрузка…
        </p>
      </div>
    )
  }

  if (!setup.keysConfigured) {
    return <SetupKeyScreen onConfigured={setup.markConfigured} />
  }

  return (
    <div className="catalog-shell flex h-screen flex-col">
      <header className="catalog-header flex shrink-0 items-center justify-between px-5">
        <div className="flex min-w-0 items-center gap-3">
          <span className="catalog-header__folder" aria-hidden="true">▱</span>
          <h1 className="truncate text-base font-semibold">Catalog — планировщик скиллов</h1>
          {gitSha ? (
            <span className="shrink-0 font-mono text-xs text-ink-faint" title="git sha">
              {gitSha}
            </span>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <ModelSelector
            provider={settingsHook.provider}
            model={settingsHook.model}
            providers={settingsHook.providers}
            models={settingsHook.models}
            loading={settingsHook.loading}
            modelsLoading={settingsHook.modelsLoading}
            onProviderChange={(p) => void settingsHook.changeProvider(p)}
            onModelChange={(m) => void settingsHook.changeModel(m)}
          />
          <button
            ref={settingsButtonRef}
            type="button"
            className="btn-icon-ghost"
            aria-label="Настройки"
            title="Настройки"
            aria-haspopup="dialog"
            aria-expanded={settingsOpen}
            onClick={() => setSettingsOpen(true)}
          >
            <SettingsIcon />
          </button>
        </div>
      </header>
      {notice && (
        <div className="catalog-notice px-5 py-2 text-xs">{notice}</div>
      )}
      <div className="catalog-layout grid flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[360px_minmax(0,1fr)]">
        <aside className="catalog-sidebar flex flex-col overflow-y-auto p-3">
          <div className="catalog-sidebar__brand">
            <span className="catalog-mark">C</span>
            <span>Catalog</span>
            <span className="catalog-sidebar__chevron">⌄</span>
          </div>
          <div className="catalog-search" role="search">
            <span aria-hidden="true">⌕</span>
            <span>Поиск</span>
          </div>
          <button
            type="button"
            className="catalog-new-chat"
            onClick={handleNewChat}
            disabled={!hasWorkspace || sessions.loading}
          >
            <span aria-hidden="true">✎</span>
            Новый чат
          </button>
          <p className="catalog-sidebar__section-label">Проект</p>
          <WorkspaceBar
            path={workspace.current?.path ?? null}
            displayName={workspace.current?.display_name ?? null}
            rescanning={rescanning}
            onOpenPicker={openPicker}
            onRescan={() => void handleRescan()}
          />
          <div className="catalog-sidebar__sections">
          <CollapsibleSection
            title="Сессии"
            open={openSessions}
            onToggle={setOpenSessions}
            actions={
              <>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={handleNewChat}
                  disabled={!hasWorkspace || sessions.loading}
                >
                  + Новый чат
                </button>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => void sessions.refresh()}
                  disabled={!hasWorkspace || sessions.loading}
                >
                  {sessions.loading ? '…' : 'Обновить'}
                </button>
              </>
            }
          >
            <SessionsPanel
              sessions={sessions}
              currentSessionId={sessionId}
              onSelect={handleSelectSession}
              onDelete={(id) => void handleDeleteSession(id)}
            />
          </CollapsibleSection>
          <CollapsibleSection
            title="Документы"
            open={openDocs}
            onToggle={setOpenDocs}
            actions={
              <button
                type="button"
                className="btn-secondary"
                onClick={() => void docs.refresh()}
                disabled={!hasWorkspace || docs.loading}
              >
                {docs.loading ? '…' : 'Обновить'}
              </button>
            }
          >
            <DocumentList
              docs={docs}
              currentDocId={currentDocId}
              onSelect={setCurrentDocId}
              uploadDisabled={!hasWorkspace}
            />
          </CollapsibleSection>
          <CollapsibleSection
            title="Скиллы"
            open={openSkills}
            onToggle={setOpenSkills}
            actions={
              <button
                type="button"
                className="btn-secondary"
                onClick={() => void skillsHook.refresh()}
                disabled={!hasWorkspace || skillsHook.loading}
              >
                {skillsHook.loading ? '…' : 'Обновить'}
              </button>
            }
          >
            <SkillsPanel
              skills={skillsHook}
              documents={docs.documents}
              defaultDocId={currentDocId}
              onApply={handleApply}
              onEdit={handleEditSkill}
              onDelete={(id) => void handleDeleteSkill(id)}
              onRename={(id, name) => skillsHook.rename(id, name)}
            />
          </CollapsibleSection>
          </div>
          <div className="catalog-sidebar__footer">
            <span className="catalog-avatar">C</span>
            <span className="truncate" title={workspace.current?.path ?? undefined}>
              {workspace.current
                ? workspace.current.display_name || workspace.current.path
                : 'Папка не открыта'}
            </span>
          </div>
        </aside>
        <main className="catalog-main overflow-hidden">
          {activeRunId ? (
            <RunView
              run={run}
              runId={activeRunId}
              documents={docs.documents}
              onClose={() => setActiveRunId(null)}
              onSaveResult={handleSaveResult}
              savingResult={savingResult}
              savedDoc={savedResultDoc}
            />
          ) : !hasWorkspace ? (
            <div className="flex h-full items-center justify-center p-6">
              <div className="max-w-sm text-center">
                <div className="mb-3 text-3xl text-ink-faint" aria-hidden="true">
                  ▱
                </div>
                <h2 className="mb-1 text-sm font-semibold text-ink">
                  Воркспейс не открыт
                </h2>
                <p className="mb-4 text-xs text-ink-faint">
                  Откройте папку, чтобы начать работу с документами и скиллами
                </p>
                <button type="button" className="btn-primary" onClick={openPicker}>
                  Открыть папку
                </button>
              </div>
            </div>
          ) : (
            <div className="flex h-full flex-col overflow-hidden">
              <div
                role="tablist"
                aria-label="Область main"
                className="flex shrink-0 gap-1 border-b border-line px-2 py-1 lg:hidden"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={mainPane === 'chat'}
                  className={
                    'rounded px-2 py-1 text-[11px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand ' +
                    (mainPane === 'chat'
                      ? 'bg-brand text-white'
                      : 'bg-surface-muted text-ink-muted')
                  }
                  onClick={() => setMainPane('chat')}
                >
                  Чат
                </button>
                <button
                  type="button"
                  role="tab"
                  aria-selected={mainPane === 'draft'}
                  className={
                    'rounded px-2 py-1 text-[11px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand ' +
                    (mainPane === 'draft'
                      ? 'bg-brand text-white'
                      : 'bg-surface-muted text-ink-muted')
                  }
                  onClick={() => setMainPane('draft')}
                >
                  Черновик
                </button>
              </div>
              <div className="flex min-h-0 flex-1 overflow-hidden">
                <div
                  role={isLg ? undefined : 'tabpanel'}
                  aria-label={isLg ? undefined : 'Чат'}
                  className={
                    'min-w-0 flex-1 overflow-hidden ' +
                    (showChat ? 'flex' : 'hidden') +
                    ' lg:flex'
                  }
                >
                  <div className="flex h-full w-full flex-col overflow-hidden">
                    <Chat
                      messages={planner.messages}
                      streaming={planner.streaming}
                      cancelling={planner.cancelling}
                      closed={planner.closed}
                      reconnecting={planner.reconnecting}
                      error={planner.error}
                      suggestions={planner.suggestions}
                      documents={docs.documents}
                      sessionDocuments={planner.sessionDocuments}
                      sessionId={sessionId}
                      onSend={handleSend}
                      onCancel={planner.cancel}
                      onReconnect={planner.reconnect}
                      onRemoveDocument={planner.removeDocument}
                      onCreateSkill={handleCreateSkill}
                      buildingSkill={buildingSkill}
                      proposingTracks={proposingTracks}
                      editingSkillName={editingSkill?.name ?? null}
                      buildError={buildError}
                      buildErrorIsTimeout={buildErrorIsTimeout}
                      sessionTimeoutSeconds={sessionTimeoutSeconds}
                      onOpenTimeoutModal={() => setTimeoutModalOpen(true)}
                      onDismissBuildError={() => {
                        setBuildError(null)
                        setBuildErrorIsTimeout(false)
                      }}
                    />
                  </div>
                </div>
                <div
                  role={isLg ? undefined : 'tabpanel'}
                  aria-label={isLg ? undefined : 'Черновик'}
                  className={
                    'catalog-draft-area w-full overflow-hidden lg:w-[408px] lg:shrink-0 ' +
                    (showDraft ? 'flex' : 'hidden') +
                    ' lg:flex'
                  }
                >
                  <div className="h-full w-full">
                    {draftPane === 'summary' ? (
                      <ArtifactSummaryCard
                        artifacts={planner.artifacts}
                        loading={planner.artifactsLoading}
                        error={planner.artifactsError}
                        streaming={planner.streaming}
                        onOpen={() => setDraftPane('editor')}
                      />
                    ) : (
                      <div className="artifact-editor h-full">
                        <div className="artifact-editor__header">
                          <div>
                            <p>Черновик</p>
                            <h2>Редактор артефактов</h2>
                          </div>
                          <button type="button" onClick={() => setDraftPane('summary')}>К сводке</button>
                        </div>
                        <div className="artifact-editor__body">
                          <ArtifactsPanel
                            sessionId={sessionId}
                            artifacts={planner.artifacts}
                            loading={planner.artifactsLoading}
                            error={planner.artifactsError}
                            streaming={planner.streaming}
                            highlightType={artifactHighlight}
                            onClearHighlight={() => setArtifactHighlight(null)}
                            onSavePrompt={planner.savePrompt}
                            onSaveScript={planner.saveScript}
                            onSaveMeta={planner.saveMeta}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
      {settingsOpen && (
        <SettingsPanel
          providers={setup.setup.providers}
          onClose={handleSettingsClose}
          onRefresh={handleSettingsRefresh}
        />
      )}
      {pickerOpen && (
        <WorkspacePicker
          recents={workspace.recents}
          browse={workspace.browse}
          open={workspace.open}
          onOpened={handleWorkspaceOpened}
          onClose={() => setPickerOpen(false)}
          onBusyConflict={handleBusyConflict}
          blocked={workspace.blocked}
          blockedReason={workspace.blockedReason}
        />
      )}
      {rescanReport && (
        <RescanReportModal report={rescanReport} onClose={handleRescanClose} />
      )}
      {settingsSkill && (
        <SkillSettingsModal
          skillId={settingsSkill.skillId}
          preview={settingsSkill.preview}
          defaultProvider={settingsHook.provider}
          defaultModel={settingsHook.model}
          onSave={handleSkillConfigured}
          onClose={() => {
            void skillsHook.refresh()
            setSettingsSkill(null)
            setEditingSkill(null)
          }}
        />
      )}
      {trackChoice && (
        <SkillTrackPicker
          tracks={trackChoice}
          onSelect={handleTrackSelect}
          onCancel={handleTrackCancel}
        />
      )}
      {timeoutModalOpen && sessionId && (
        <SessionTimeoutModal
          currentSeconds={sessionTimeoutSeconds}
          onSave={handleSaveSessionTimeout}
          onClose={() => setTimeoutModalOpen(false)}
        />
      )}
    </div>
  )
}
