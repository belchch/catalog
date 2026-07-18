import { useCallback, useEffect, useState } from 'react'
import type { ApplyMode, SkillOut } from '../api.ts'
import { applySkill, commitSkill, deleteSkill, listSkills } from '../api.ts'

export interface UseSkillsResult {
  skills: SkillOut[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  commit: (skillId: string) => Promise<void>
  apply: (skillId: string, docIds: string[], mode?: ApplyMode) => Promise<string>
  remove: (skillId: string) => Promise<void>
}

export function useSkills(): UseSkillsResult {
  const [skills, setSkills] = useState<SkillOut[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setSkills(await listSkills())
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [])

  const commit = useCallback(async (skillId: string) => {
    await commitSkill(skillId)
    setSkills((prev) =>
      prev.map((s) => (s.id === skillId ? { ...s, status: 'committed' } : s)),
    )
  }, [])

  const apply = useCallback(
    async (skillId: string, docIds: string[], mode: ApplyMode = 'persist') => {
      const { run_id } = await applySkill(skillId, docIds, mode)
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

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { skills, loading, error, refresh, commit, apply, remove }
}
