import { useCallback, useEffect, useRef, useState } from 'react'
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

export function persistLocalSettings(s: PersistedSettings) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(s))
  } catch {
  }
}

export function useSettings(enabled = true) {
  const [provider, setProvider] = useState('')
  const [model, setModel] = useState('')
  const [providers, setProviders] = useState<ProviderOut[]>([])
  const [models, setModels] = useState<ModelOut[]>([])
  const [loading, setLoading] = useState(enabled)
  const [modelsLoading, setModelsLoading] = useState(false)
  const providerChangeSeq = useRef(0)

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }
    let cancelled = false
    void (async () => {
      setLoading(true)
      try {
        const [ps, remote] = await Promise.all([listProviders(), getSettings()])
        if (cancelled) return
        setProviders(ps)
        const local = readLocal()
        const initProvider = local?.provider || remote.provider
        const initModel = local?.model || remote.model
        setProvider(initProvider)
        setModel(initModel)
        if (local && (local.provider !== remote.provider || local.model !== remote.model)) {
          try {
            await updateSettings(local)
          } catch {
            if (cancelled) return
            setProvider(remote.provider)
            setModel(remote.model)
            persistLocalSettings({ provider: remote.provider, model: remote.model })
          }
        }
        if (initProvider) {
          try {
            const nextModels = await getProviderModels(initProvider)
            if (!cancelled) setModels(nextModels)
          } catch {
            if (!cancelled) setModels([])
          }
        }
      } catch {
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [enabled])

  const changeProvider = useCallback(async (newProvider: string) => {
    const seq = ++providerChangeSeq.current
    setProvider(newProvider)
    setModelsLoading(true)
    setModels([])
    setModel('')
    try {
      let newModels: ModelOut[]
      try {
        newModels = await getProviderModels(newProvider)
      } catch {
        if (seq !== providerChangeSeq.current) return
        setModels([])
        setModel('')
        return
      }
      if (seq !== providerChangeSeq.current) return
      setModels(newModels)
      const newModel = newModels[0]?.id ?? ''
      setModel(newModel)
      const next = { provider: newProvider, model: newModel }
      persistLocalSettings(next)
      await updateSettings(next)
    } finally {
      if (seq === providerChangeSeq.current) {
        setModelsLoading(false)
      }
    }
  }, [])

  const changeModel = useCallback(
    async (newModel: string) => {
      setModel(newModel)
      const next = { provider, model: newModel }
      persistLocalSettings(next)
      await updateSettings(next)
    },
    [provider],
  )

  const refreshProviders = useCallback(async () => {
    const ps = await listProviders()
    setProviders(ps)
  }, [])

  return {
    provider,
    model,
    providers,
    models,
    loading,
    modelsLoading,
    changeProvider,
    changeModel,
    refreshProviders,
  }
}
