import type { ModelOut } from '../api.ts'

const COMPARE_OPTS: Intl.CollatorOptions = { sensitivity: 'base', numeric: true }

export function sortAndFilterModels(models: ModelOut[], query: string): ModelOut[] {
  const q = query.trim().toLowerCase()
  const filtered = q
    ? models.filter(
        (m) => m.name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q),
      )
    : models
  return [...filtered].sort((a, b) => {
    const aKey = a.name || a.id
    const bKey = b.name || b.id
    return aKey.localeCompare(bKey, undefined, COMPARE_OPTS)
  })
}
