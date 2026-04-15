import { useEffect, useState } from 'react'
import { api } from '../api'

export default function StatusBar() {
  const [status, setStatus] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)

  async function refresh() {
    try {
      const data = await api.status()
      setStatus(data)
      setLastUpdated(new Date())
    } catch {
      setStatus(null)
    }
  }

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 30_000)
    return () => clearInterval(id)
  }, [])

  const llmOk = status?.llm_available

  return (
    <header className="sticky top-0 z-20 bg-jarvis-bg border-b border-jarvis-border px-4 py-2 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className="text-jarvis-accent font-semibold tracking-widest text-sm">J.A.R.V.I.S.</span>
        <span className="text-jarvis-dim text-xs hidden sm:block">Household Operating System</span>
      </div>

      <div className="flex items-center gap-4 text-xs">
        <span className="flex items-center gap-1.5">
          <span className={llmOk ? 'dot-online' : 'dot-offline'} />
          <span className={llmOk ? 'text-jarvis-green' : 'text-jarvis-red'}>
            LLM {status ? (llmOk ? 'online' : 'offline') : '…'}
          </span>
        </span>

        {status && (
          <span className="text-jarvis-dim hidden sm:block">
            {status.adapter_count} adapters
          </span>
        )}

        {lastUpdated && (
          <span className="text-jarvis-dim hidden md:block">
            {lastUpdated.toLocaleTimeString()}
          </span>
        )}

        <button
          onClick={refresh}
          className="text-jarvis-dim hover:text-gray-300 transition-colors"
          title="Refresh"
        >
          ↻
        </button>
      </div>
    </header>
  )
}
