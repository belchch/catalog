import { useCallback, useEffect, useState } from 'react'
import {
  getProviderModels,
  getSettings,
  listProviders,
  updateSettings,
  type ModelOut,
  type ProviderOut,
} from '../api.ts'

const LS_KEY = 'catalog.settings'

interface PersistedSettings {
  provider: string
  model: string
}

function readLocal(): PersistedSettings | null {
  try {
    const raw = localStorage.getItem(LS_KEY)
    return raw ? (JSON.parse(raw) as PersistedSettings) : null
  } catch {
    return null
  }
}

function writeLocal(s: PersistedSettings) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(s))
  } catch {
    // Ignore storage failures (private mode etc.) — backend is still updated.
  }
}

/**
 * Runtime model/provider selection (CATALOG-14). The choice is seeded from the
 * backend (env default), persisted to localStorage so it survives a page
 * reload, and synced back to the backend on every change so the planner/apply
 * pick it up.
 */
export function useSettings() {
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [providers, setProviders] = useState<ProviderOut[]>([])
  const [models, setModels] = useState<ModelOut[]>([])
  const [loading, setLoading] = useState(true)

  // Initial load: prefer localStorage, fall back to the backend's current state.
  useEffect(() => {
    void (async () => {
      setLoading(true)
      try {
        const [ps, remote] = await Promise.all([listProviders(), getSettings()])
        setProviders(ps)
        const local = readLocal()
        const initProvider = local?.provider || remote.provider
        const initModel = local?.model || remote.model
        setProvider(initProvider)
        setModel(initModel)
        // If a local choice differs from the backend, push it up.
        if (local && (local.provider !== remote.provider || local.model !== remote.model)) {
          await updateSettings(local)
        }
        if (initProvider) {
          setModels(await getProviderModels(initProvider))
        }
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  const changeProvider = useCallback(async (newProvider: string) => {
    setProvider(newProvider)
    const newModels = await getProviderModels(newProvider)
    setModels(newModels)
    // Reset model to the first available under the new provider.
    const newModel = newModels[0]?.id ?? ''
    setModel(newModel)
    const next = { provider: newProvider, model: newModel }
    writeLocal(next)
    await updateSettings(next)
  }, [])

  const changeModel = useCallback(
    async (newModel: string) => {
      setModel(newModel)
      const next = { provider, model: newModel }
      writeLocal(next)
      await updateSettings(next)
    },
    [provider],
  )

  return { provider, model, providers, models, loading, changeProvider, changeModel }
}
