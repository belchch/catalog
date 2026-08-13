import { useCallback, useEffect, useState } from 'react'
import { getSetup, type SetupOut } from '../api.ts'

export type SetupLoadStatus = 'unknown' | 'ready'

export function useSetup() {
  const [status, setStatus] = useState<SetupLoadStatus>('unknown')
  const [keysConfigured, setKeysConfigured] = useState(false)

  useEffect(() => {
    let cancelled = false
    void getSetup()
      .then((s) => {
        if (cancelled) return
        setKeysConfigured(s.keys_configured)
        setStatus('ready')
      })
      .catch(() => {
        if (cancelled) return
        setKeysConfigured(false)
        setStatus('ready')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const markConfigured = useCallback((s: SetupOut) => {
    setKeysConfigured(s.keys_configured)
    setStatus('ready')
  }, [])

  return { status, keysConfigured, markConfigured }
}
