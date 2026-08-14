import { useCallback, useEffect, useState } from 'react'
import { getSetup, type SetupOut } from '../api.ts'

export type SetupLoadStatus = 'unknown' | 'ready'

const EMPTY_SETUP: SetupOut = {
  keys_configured: false,
  provider: '',
  openrouter_configured: false,
  zai_configured: false,
  providers: [],
}

function normalizeSetup(s: SetupOut): SetupOut {
  return { ...s, providers: s.providers ?? [] }
}

export function useSetup() {
  const [status, setStatus] = useState<SetupLoadStatus>('unknown')
  const [setup, setSetup] = useState<SetupOut>(EMPTY_SETUP)
  const [keysConfigured, setKeysConfigured] = useState(false)

  const applySetup = useCallback((s: SetupOut) => {
    const next = normalizeSetup(s)
    setSetup(next)
    setKeysConfigured(next.keys_configured)
    setStatus('ready')
  }, [])

  useEffect(() => {
    let cancelled = false
    void getSetup()
      .then((s) => {
        if (cancelled) return
        applySetup(s)
      })
      .catch(() => {
        if (cancelled) return
        applySetup(EMPTY_SETUP)
      })
    return () => {
      cancelled = true
    }
  }, [applySetup])

  const markConfigured = useCallback(
    (s: SetupOut) => {
      applySetup(s)
    },
    [applySetup],
  )

  const refresh = useCallback(async () => {
    const s = await getSetup()
    applySetup(s)
  }, [applySetup])

  return { status, keysConfigured, setup, markConfigured, refresh }
}
