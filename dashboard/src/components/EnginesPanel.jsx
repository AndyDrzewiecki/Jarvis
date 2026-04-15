import { useEffect, useState } from 'react'
import { api } from '../api'

const ENGINE_ICONS = {
  financial:    '💹',
  research:     '🔬',
  geopolitical: '🌍',
  legal:        '⚖️',
  health:       '🏥',
  local:        '📍',
  family:       '👨‍👩‍👧',
}

function fmt(n) {
  if (n == null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function timeAgo(iso) {
  if (!iso) return null
  const diff = (Date.now() - new Date(iso)) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

export default function EnginesPanel() {
  const [engines, setEngines] = useState([])
  const [totalRecords, setTotalRecords] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expanded, setExpanded] = useState(null)

  async function refresh() {
    try {
      const data = await api.enginesStatus()
      setEngines(data.engines)
      setTotalRecords(data.total_records)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 60_000)
    return () => clearInterval(id)
  }, [])

  if (loading) return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
      {Array.from({ length: 7 }).map((_, i) => (
        <div key={i} className="card h-28 animate-pulse bg-jarvis-border/20" />
      ))}
    </div>
  )
  if (error) return <p className="text-jarvis-red text-sm p-4">{error}</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Knowledge Engines</h2>
          <p className="text-xs text-jarvis-dim">{fmt(totalRecords)} total records across 7 engines</p>
        </div>
        <button onClick={refresh} className="btn-ghost text-xs">↻ refresh</button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {engines.map(engine => (
          <EngineCard
            key={engine.name}
            engine={engine}
            expanded={expanded === engine.name}
            onToggle={() => setExpanded(expanded === engine.name ? null : engine.name)}
          />
        ))}
      </div>
    </div>
  )
}

function EngineCard({ engine, expanded, onToggle }) {
  const ago = timeAgo(engine.last_run)
  const tables = Object.entries(engine.tables)

  return (
    <div className="card flex flex-col gap-2 cursor-pointer" onClick={onToggle}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">{ENGINE_ICONS[engine.name] || '🗄️'}</span>
          <div>
            <div className="text-sm font-medium text-gray-200 capitalize">{engine.name}</div>
            <div className="text-xs text-jarvis-dim">{tables.length} tables</div>
          </div>
        </div>
        <span className="text-jarvis-accent font-mono font-semibold text-sm">
          {fmt(engine.total_records)}
        </span>
      </div>

      {expanded && (
        <div className="border-t border-jarvis-border pt-2 space-y-1">
          {tables.map(([table, count]) => (
            <div key={table} className="flex justify-between text-xs">
              <span className="text-jarvis-dim truncate">{table}</span>
              <span className="text-gray-300 font-mono ml-2">{fmt(count)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="text-xs text-jarvis-dim mt-auto border-t border-jarvis-border pt-2">
        {ago ? `last ingest ${ago}` : 'never ingested'} · {expanded ? '▲ collapse' : '▼ tables'}
      </div>
    </div>
  )
}
