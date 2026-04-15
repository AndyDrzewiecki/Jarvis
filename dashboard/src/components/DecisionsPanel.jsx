import { useEffect, useState } from 'react'
import { api } from '../api'

const OUTCOME_CLASS = {
  success: 'badge-success',
  failure: 'badge-failure',
  error:   'badge-failure',
  unknown: 'badge-idle',
}

function outcomeClass(o) {
  return OUTCOME_CLASS[o] ?? 'badge-idle'
}

export default function DecisionsPanel() {
  const [decisions, setDecisions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [agentFilter, setAgentFilter] = useState('')
  const [limit, setLimit] = useState(50)
  const [agents, setAgents] = useState([])

  async function refresh() {
    setLoading(true)
    try {
      const data = await api.decisions({
        agent: agentFilter || undefined,
        limit,
      })
      setDecisions(data.decisions)
      // Build unique agent list from all loaded decisions
      const all = await api.recentDecisions(200)
      setAgents([...new Set(all.decisions.map(d => d.agent))].sort())
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [agentFilter, limit])

  function formatTime(iso) {
    if (!iso) return '—'
    const d = new Date(iso)
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    })
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Decision Audit Log</h2>
          <p className="text-xs text-jarvis-dim">{decisions.length} decisions loaded</p>
        </div>
        <button onClick={refresh} className="btn-ghost text-xs">↻ refresh</button>
      </div>

      <div className="flex flex-wrap gap-2 mb-3">
        <select
          value={agentFilter}
          onChange={e => setAgentFilter(e.target.value)}
          className="input w-auto bg-jarvis-bg text-sm"
        >
          <option value="">All agents</option>
          {agents.map(a => <option key={a} value={a}>{a}</option>)}
        </select>

        <select
          value={limit}
          onChange={e => setLimit(Number(e.target.value))}
          className="input w-auto bg-jarvis-bg text-sm"
        >
          {[20, 50, 100, 200, 500].map(n => (
            <option key={n} value={n}>{n} rows</option>
          ))}
        </select>
      </div>

      {error && <p className="text-jarvis-red text-sm mb-3">{error}</p>}

      {loading ? (
        <div className="space-y-1">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-8 rounded bg-jarvis-border/20 animate-pulse" />
          ))}
        </div>
      ) : decisions.length === 0 ? (
        <p className="text-jarvis-dim text-sm p-8 text-center">No decisions logged yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-jarvis-dim border-b border-jarvis-border">
                <th className="text-left py-2 pr-3 font-medium whitespace-nowrap w-36">Time</th>
                <th className="text-left py-2 pr-3 font-medium w-32">Agent</th>
                <th className="text-left py-2 pr-3 font-medium w-32">Capability</th>
                <th className="text-left py-2 pr-3 font-medium">Decision</th>
                <th className="text-left py-2 pr-3 font-medium w-20">Outcome</th>
                <th className="text-right py-2 font-medium w-16">ms</th>
              </tr>
            </thead>
            <tbody>
              {[...decisions].reverse().map((d, i) => (
                <tr key={d.id ?? i} className="border-b border-jarvis-border/40 hover:bg-white/5 transition-colors">
                  <td className="py-1.5 pr-3 text-jarvis-dim whitespace-nowrap">
                    {formatTime(d.timestamp)}
                  </td>
                  <td className="py-1.5 pr-3 text-jarvis-accent truncate max-w-[8rem]">
                    {d.agent}
                  </td>
                  <td className="py-1.5 pr-3 text-gray-400 truncate max-w-[8rem]">
                    {d.capability}
                  </td>
                  <td className="py-1.5 pr-3 text-gray-300 leading-relaxed">
                    {(d.decision ?? '').slice(0, 100)}
                    {(d.decision ?? '').length > 100 && '…'}
                  </td>
                  <td className="py-1.5 pr-3">
                    <span className={outcomeClass(d.outcome)}>{d.outcome}</span>
                  </td>
                  <td className="py-1.5 text-right text-jarvis-dim font-mono">
                    {d.duration_ms ?? '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
