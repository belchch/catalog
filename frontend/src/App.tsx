import { useCallback, useState } from 'react'
import { buildSkill, createSession, type SkillPreview } from './api.ts'
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

  const planner = usePlannerSession(sessionId)
  const run = useRunStream(activeRunId)

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
    async (skillId: string, docIds: string[]) => {
      setNotice(null)
      try {
        const runId = await skillsHook.apply(skillId, docIds)
        setActiveRunId(runId)
      } catch (e) {
        setNotice(e instanceof Error ? e.message : String(e))
      }
    },
    [skillsHook],
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
          />
        </aside>
        <main className="overflow-hidden">
          {activeRunId ? (
            <RunView run={run} runId={activeRunId} onClose={() => setActiveRunId(null)} />
          ) : (
            <Chat
              messages={planner.messages}
              streaming={planner.streaming}
              cancelling={planner.cancelling}
              closed={planner.closed}
              error={planner.error}
              onSend={handleSend}
              onCancel={planner.cancel}
              onCreateSkill={handleCreateSkill}
              buildingSkill={buildingSkill}
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
          }}
        />
      )}
    </div>
  )
}
