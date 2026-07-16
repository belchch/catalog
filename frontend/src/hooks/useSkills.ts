import { useCallback, useEffect, useState } from 'react'
import type { SkillOut } from '../api.ts'
import { applySkill, commitSkill, listSkills } from '../api.ts'

export interface UseSkillsResult {
  skills: SkillOut[]
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
  commit: (skillId: string) => Promise<void>
  apply: (skillId: string, docIds: string[]) => Promise<string>
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

  const apply = useCallback(async (skillId: string, docIds: string[]) => {
    const { run_id } = await applySkill(skillId, docIds)
    return run_id
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  return { skills, loading, error, refresh, commit, apply }
}
