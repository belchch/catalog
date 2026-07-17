import { useCallback, useEffect, useState } from 'react'
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
import { DocumentList } from './components/DocumentList.tsx'
import { ModelSelector } from './components/ModelSelector.tsx'
import { RunView } from './components/RunView.tsx'
import { SkillSettingsModal } from './components/SkillSettingsModal.tsx'
import { SkillsPanel } from './components/SkillsPanel.tsx'
import { useDocuments } from './hooks/useDocuments.ts'
import { usePlannerSession } from './hooks/usePlannerSession.ts'
import { useRunStream } from './hooks/useRunStream.ts'
import { useSettings } from './hooks/useSettings.ts'
import { useSkills } from './hooks/useSkills.ts'

export default function App() {
  const docs = useDocuments()
  const skillsHook = useSkills()
  const settingsHook = useSettings()

  const [sessionId, setSessionId] = useState<string | null>(null)
  const [currentDocId, setCurrentDocId] = useState<string | null>(null)
  const [buildingSkill, setBuildingSkill] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  // CATALOG-6: skill being configured in the pre-save settings modal.
  const [settingsSkill, setSettingsSkill] = useState<{ skillId: string; preview: SkillPreview } | null>(null)
  // CATALOG-17: set while the chat is editing an existing skill (vs. building
  // a brand new one) — drives the "Сохранить изменения" button and banner.
  const [editingSkill, setEditingSkill] = useState<{ skillId: string; name: string } | null>(null)
  // CATALOG-18: the doc a "на экран" result was just saved into, plus its
  // in-flight state — cleared whenever a new run starts.
  const [savedResultDoc, setSavedResultDoc] = useState<DocumentOut | null>(null)
  const [savingResult, setSavingResult] = useState(false)

  const planner = usePlannerSession(sessionId)
  const run = useRunStream(activeRunId)

  // "В док" runs create their result document server-side — refresh the list
  // so it shows up without the user having to click "Обновить".
  useEffect(() => {
    if (run.finished && run.status === 'ok' && run.outputDocId) {
      void docs.refresh()
    }
  }, [run.finished, run.status, run.outputDocId, docs])

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId
    const created = await createSession()
    setSessionId(created.id)
    return created.id
  }, [sessionId])

  const handleSend = useCallback(
    async (text: string) => {
      try {
        await ensureSession()
        planner.send(text)
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e))
      }
    },
    [ensureSession, planner],
  )

  const handleEditSkill = useCallback(async (skillId: string, name: string) => {
    setNotice(null)
    try {
      const started = await startEditSession(skillId)
      setActiveRunId(null)
      setSessionId(started.session_id)
      setEditingSkill({ skillId: started.skill_id, name })
    } catch (e) {
      setNotice(e instanceof Error ? e.message : String(e))
    }
  }, [])

  const handleCreateSkill = useCallback(async () => {
    if (!sessionId) return
    setBuildingSkill(true)
    setNotice(null)
    try {
      const built = await buildSkill(sessionId)
      // CATALOG-6: open the settings modal with the preview config instead of
      // silently dropping the draft — the user finalizes model/provider/reasoning.
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
        const runId = await skillsHook.apply(skillId, docIds, mode)
        setActiveRunId(runId)
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e))
      }
    },
    [skillsHook],
  )

  const handleSaveResult = useCallback(
    async (runId: string) => {
      setSavingResult(true)
      setNotice(null)
      try {
        const doc = await saveRunResult(runId)
        setSavedResultDoc(doc)
        await docs.refresh()
        setCurrentDocId(doc.id)
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e))
      } finally {
        setSavingResult(false)
      }
    },
    [docs],
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
          <DocumentList docs={docs} currentDocId={currentDocId} onSelect={setCurrentDocId} />
          <SkillsPanel
            skills={skillsHook}
            documents={docs.documents}
            defaultDocId={currentDocId}
            onApply={handleApply}
            onEdit={handleEditSkill}
          />
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
              error={planner.error}
              suggestions={planner.suggestions}
              onSend={handleSend}
              onCancel={planner.cancel}
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
          onSave={handleSkillConfigured}
          onClose={() => {
            // Refresh even on cancel so the created draft appears in the list.
            void skillsHook.refresh()
            setSettingsSkill(null)
            setEditingSkill(null)
          }}
        />
      )}
    </div>
  )
}
