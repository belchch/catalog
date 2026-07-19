import { useCallback, useEffect, useRef, useState } from 'react'
import {
  buildSkill,
  createSession,
  saveRunResult,
  startEditSession,
  type ApplyMode,
  type DocumentOut,
  type SkillPreview,
} from './api.ts'
import { Chat } from './components/Chat.tsx'
import { CollapsibleSection } from './components/CollapsibleSection.tsx'
import { DocumentList } from './components/DocumentList.tsx'
import { ModelSelector } from './components/ModelSelector.tsx'
import { RunView } from './components/RunView.tsx'
import { SessionsPanel } from './components/SessionsPanel.tsx'
import { SkillSettingsModal } from './components/SkillSettingsModal.tsx'
import { SkillsPanel } from './components/SkillsPanel.tsx'
import { useDocuments } from './hooks/useDocuments.ts'
import { usePlannerSession } from './hooks/usePlannerSession.ts'
import { useRunStream } from './hooks/useRunStream.ts'
import { useSessions } from './hooks/useSessions.ts'
import { useSettings } from './hooks/useSettings.ts'
import { useSkills } from './hooks/useSkills.ts'

const SESSION_STORAGE_KEY = 'catalog.sessionId'

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

export default function App() {
  const docs = useDocuments()
  const skillsHook = useSkills()
  const settingsHook = useSettings()
  const sessions = useSessions()

  const [sessionId, setSessionId] = useState<string | null>(() => readStoredSessionId())
  const [currentDocId, setCurrentDocId] = useState<string | null>(null)
  const [buildingSkill, setBuildingSkill] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [settingsSkill, setSettingsSkill] = useState<{ skillId: string; preview: SkillPreview } | null>(null)
  const [editingSkill, setEditingSkill] = useState<{ skillId: string; name: string } | null>(null)
  const [savedResultDoc, setSavedResultDoc] = useState<DocumentOut | null>(null)
  const [savingResult, setSavingResult] = useState(false)
  const [openSessions, setOpenSessions] = useState(false)
  const [openDocs, setOpenDocs] = useState(false)
  const [openSkills, setOpenSkills] = useState(false)

  const handleSessionInvalid = useCallback(() => {
    writeStoredSessionId(null)
    setSessionId(null)
    setEditingSkill(null)
  }, [])

  const planner = usePlannerSession(sessionId, { onSessionInvalid: handleSessionInvalid })
  const { refreshSessionDocuments } = planner
  const run = useRunStream(activeRunId)

  useEffect(() => {
    writeStoredSessionId(sessionId)
  }, [sessionId])

  useEffect(() => {
    if (!run.finished) return
    if (run.status === 'ok' && run.outputDocId) {
      void docs.refresh()
    }
    void refreshSessionDocuments()
  }, [run.finished, run.status, run.outputDocId, docs, refreshSessionDocuments])

  const wasStreamingRef = useRef(false)
  useEffect(() => {
    if (wasStreamingRef.current && !planner.streaming) {
      void sessions.refresh()
    }
    wasStreamingRef.current = planner.streaming
  }, [planner.streaming, sessions])

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

  const handleCreateSkill = useCallback(async () => {
    if (!sessionId) return
    setBuildingSkill(true)
    setNotice(null)
    try {
      const built = await buildSkill(sessionId)
      setSettingsSkill({ skillId: built.skill_id, preview: built.config })
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    } finally {
      setBuildingSkill(false)
    }
  }, [sessionId])

  const handleSkillConfigured = useCallback(async () => {
    await skillsHook.refresh()
    setNotice('Скилл настроен (draft). Сделайте коммит, затем примените к документу.')
  }, [skillsHook])

  const handleApply = useCallback(
    async (skillId: string, docIds: string[], mode: ApplyMode) => {
      setNotice(null)
      setSavedResultDoc(null)
      try {
        const sid = await ensureSession()
        const runId = await skillsHook.apply(skillId, docIds, mode, sid)
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
      <div className="grid flex-1 grid-cols-1 overflow-hidden md:grid-cols-[320px_1fr]">
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
              editingSkillName={editingSkill?.name ?? null}
            />
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
    </div>
  )
}
