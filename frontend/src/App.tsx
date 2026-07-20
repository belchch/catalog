import { useCallback, useEffect, useRef, useState } from 'react'
import {
  buildSkill,
  createSession,
  extractApiDetail,
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
  type SkillPreview,
  type SkillTrack,
} from './api.ts'
import { ArtifactsPanel } from './components/ArtifactsPanel.tsx'
import { Chat } from './components/Chat.tsx'
import { CollapsibleSection } from './components/CollapsibleSection.tsx'
import { DocumentList } from './components/DocumentList.tsx'
import { ModelSelector } from './components/ModelSelector.tsx'
import { RunView } from './components/RunView.tsx'
import { SessionsPanel } from './components/SessionsPanel.tsx'
import { SessionTimeoutModal } from './components/SessionTimeoutModal.tsx'
import { SkillSettingsModal } from './components/SkillSettingsModal.tsx'
import { SkillTrackPicker } from './components/SkillTrackPicker.tsx'
import { SkillsPanel } from './components/SkillsPanel.tsx'
import { useDocuments } from './hooks/useDocuments.ts'
import { usePlannerSession } from './hooks/usePlannerSession.ts'
import { useRunStream } from './hooks/useRunStream.ts'
import { useSessions } from './hooks/useSessions.ts'
import { useSettings } from './hooks/useSettings.ts'
import { useSkills } from './hooks/useSkills.ts'

const SESSION_STORAGE_KEY = 'catalog.sessionId'

type MainPane = 'chat' | 'draft'

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
  const docs = useDocuments()
  const skillsHook = useSkills()
  const settingsHook = useSettings()
  const sessions = useSessions()
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
  const [artifactHighlight, setArtifactHighlight] = useState<ArtifactType | null>(null)

  const handleSessionInvalid = useCallback(() => {
    writeStoredSessionId(null)
    setSessionId(null)
    setEditingSkill(null)
    setArtifactHighlight(null)
  }, [])

  const planner = usePlannerSession(sessionId, { onSessionInvalid: handleSessionInvalid })
  const { refreshSessionDocuments } = planner
  const run = useRunStream(activeRunId)
  const docsRefresh = docs.refresh
  const sessionsRefresh = sessions.refresh

  useEffect(() => {
    writeStoredSessionId(sessionId)
  }, [sessionId])

  useEffect(() => {
    setArtifactHighlight(null)
    setMainPane('chat')
    setBuildError(null)
    setBuildErrorIsTimeout(false)
    setTimeoutModalOpen(false)
  }, [sessionId])

  useEffect(() => {
    if (!sessionId) {
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
  }, [sessionId, sessions.sessions])

  const handledRunFinishRef = useRef<string | null>(null)
  useEffect(() => {
    if (!run.finished || !activeRunId) return
    if (handledRunFinishRef.current === activeRunId) return
    handledRunFinishRef.current = activeRunId
    if (run.status === 'ok' && run.outputDocId) {
      void docsRefresh()
    }
    void refreshSessionDocuments()
  }, [run.finished, run.status, run.outputDocId, activeRunId, docsRefresh, refreshSessionDocuments])

  const wasStreamingRef = useRef(false)
  useEffect(() => {
    if (wasStreamingRef.current && !planner.streaming) {
      void sessionsRefresh()
    }
    wasStreamingRef.current = planner.streaming
  }, [planner.streaming, sessionsRefresh])

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId
    const created = await createSession()
    setSessionId(created.id)
    void sessions.refresh()
    return created.id
  }, [sessionId, sessions])

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
    } finally {
      setProposingTracks(false)
    }

    if (
      !proposed ||
      proposed.skipped ||
      proposed.fallback ||
      proposed.tracks.length === 0
    ) {
      await runBuildSkill(sessionId)
      return
    }

    if (proposed.tracks.length === 1) {
      try {
        await selectSkillTrack(sessionId, proposed.tracks[0])
      } catch {}
      await runBuildSkill(sessionId)
      return
    }

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

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-800 px-4 py-2">
        <h1 className="text-base font-semibold">Catalog — планировщик скиллов</h1>
        <ModelSelector
          provider={settingsHook.provider}
          model={settingsHook.model}
          providers={settingsHook.providers}
          models={settingsHook.models}
          loading={settingsHook.loading}
          onProviderChange={(p) => void settingsHook.changeProvider(p)}
          onModelChange={(m) => void settingsHook.changeModel(m)}
        />
      </header>
      {notice && (
        <div className="bg-slate-800/60 px-4 py-1 text-xs text-slate-300">{notice}</div>
      )}
      <div className="grid flex-1 grid-cols-1 overflow-hidden md:grid-cols-[352px_1fr]">
        <aside className="flex flex-col gap-4 overflow-y-auto border-r border-slate-800 p-3">
          <CollapsibleSection
            title="Сессии"
            open={openSessions}
            onToggle={setOpenSessions}
            actions={
              <>
                <button
                  type="button"
                  className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-50"
                  onClick={handleNewChat}
                  disabled={sessions.loading}
                >
                  + Новый чат
                </button>
                <button
                  type="button"
                  className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-50"
                  onClick={() => void sessions.refresh()}
                  disabled={sessions.loading}
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
                className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-50"
                onClick={() => void docs.refresh()}
                disabled={docs.loading}
              >
                {docs.loading ? '…' : 'Обновить'}
              </button>
            }
          >
            <DocumentList docs={docs} currentDocId={currentDocId} onSelect={setCurrentDocId} />
          </CollapsibleSection>
          <CollapsibleSection
            title="Скиллы"
            open={openSkills}
            onToggle={setOpenSkills}
            actions={
              <button
                type="button"
                className="rounded bg-slate-800 px-2 py-1 text-xs text-slate-300 hover:bg-slate-700 disabled:opacity-50"
                onClick={() => void skillsHook.refresh()}
                disabled={skillsHook.loading}
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
        </aside>
        <main className="overflow-hidden">
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
          ) : (
            <div className="flex h-full flex-col overflow-hidden">
              <div
                role="tablist"
                aria-label="Область main"
                className="flex shrink-0 gap-1 border-b border-slate-800 px-2 py-1 lg:hidden"
              >
                <button
                  type="button"
                  role="tab"
                  aria-selected={mainPane === 'chat'}
                  className={
                    'rounded px-2 py-1 text-[11px] ' +
                    (mainPane === 'chat'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-800 text-slate-300')
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
                    'rounded px-2 py-1 text-[11px] ' +
                    (mainPane === 'draft'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-800 text-slate-300')
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
                    'w-full overflow-hidden lg:w-[420px] lg:shrink-0 ' +
                    (showDraft ? 'flex' : 'hidden') +
                    ' lg:flex'
                  }
                >
                  <div className="h-full w-full">
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
              </div>
            </div>
          )}
        </main>
      </div>
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
