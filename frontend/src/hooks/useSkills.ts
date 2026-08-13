import { useCallback, useEffect, useState } from 'react'
import type { ApplyMode, SkillOut } from '../api.ts'
import { applySkill, commitSkill, deleteSkill, listSkills, renameSkill } from '../api.ts'

export interface UseSkillsResult {
  skills: SkillOut[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  commit: (skillId: string) => Promise<void>
  apply: (
    skillId: string,
    docIds: string[],
    mode?: ApplyMode,
    sessionId?: string | null,
    prompt?: string,
  ) => Promise<string>
  remove: (skillId: string) => Promise<void>
  rename: (skillId: string, name: string) => Promise<void>
}

export function useSkills(enabled = true): UseSkillsResult {
  const [skills, setSkills] = useState<SkillOut[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!enabled) {
      setSkills([])
      setError(null)
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      setSkills(await listSkills())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [enabled])

  const commit = useCallback(async (skillId: string) => {
    await commitSkill(skillId)
    setSkills((prev) =>
      prev.map((s) => (s.id === skillId ? { ...s, status: 'committed' } : s)),
    )
  }, [])

  const apply = useCallback(
    async (
      skillId: string,
      docIds: string[],
      mode: ApplyMode = 'persist',
      sessionId?: string | null,
      prompt?: string,
    ) => {
      const { run_id } = await applySkill(skillId, docIds, mode, sessionId, prompt)
      return run_id
    },
    [],
  )

  const remove = useCallback(async (skillId: string) => {
    setError(null)
    try {
      await deleteSkill(skillId)
      setSkills((prev) => prev.filter((s) => s.id !== skillId))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      throw e
    }
  }, [])

  const rename = useCallback(async (skillId: string, name: string) => {
    setError(null)
    try {
      const updated = await renameSkill(skillId, name)
      setSkills((prev) =>
        prev.map((s) => (s.id === skillId ? { ...s, name: updated.name } : s)),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      throw e
    }
  }, [])

  useEffect(() => {
    if (!enabled) {
      setSkills([])
      setError(null)
      setLoading(false)
      return
    }
    void refresh()
  }, [refresh, enabled])

  return { skills, loading, error, refresh, commit, apply, remove, rename }
}
