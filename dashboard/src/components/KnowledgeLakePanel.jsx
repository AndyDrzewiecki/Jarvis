import { useEffect, useState } from 'react'
import { api } from '../api'

const DOMAINS = ['', 'grocery', 'finance', 'calendar', 'home', 'news', 'investor',
                 'health', 'weather', 'security', 'general']

function confidenceBar(v) {
  const pct = Math.round((v ?? 0) * 100)
  const color = pct >= 80 ? 'bg-jarvis-green' : pct >= 50 ? 'bg-jarvis-yellow' : 'bg-jarvis-red'
  return (
    <div className="flex items-center gap-1.5">
      <div className="w-16 bg-jarvis-border rounded-full h-1.5 overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-jarvis-dim w-8">{pct}%</span>
    </div>
  )
}

function timeAgo(iso) {
  if (!iso) return '—'
  const diff = (Date.now() - new Date(iso)) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

export default function KnowledgeLakePanel() {
  const [facts, setFacts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [domain, setDomain] = useState('')
  const [search, setSearch] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [limit, setLimit] = useState(50)

  async function refresh() {
    setLoading(true)
    try {
      const data = await api.knowledgeLake({
        domain: domain || undefined,
        q: search || undefined,
        limit,
      })
      setFacts(data.facts)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [domain, search, limit])

  function handleSearch(e) {
    e.preventDefault()
    setSearch(searchInput)
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Knowledge Lake</h2>
          <p className="text-xs text-jarvis-dim">{facts.length} facts loaded</p>
        </div>
        <button onClick={refresh} className="btn-ghost text-xs">↻ refresh</button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-3">
        <select
          value={domain}
          onChange={e => setDomain(e.target.value)}
          className="input w-auto bg-jarvis-bg text-sm"
        >
          <option value="">All domains</option>
          {DOMAINS.filter(Boolean).map(d => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>

        <form onSubmit={handleSearch} className="flex gap-1 flex-1 min-w-0">
          <input
            className="input flex-1"
            placeholder="Search facts…"
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
          />
          <button type="submit" className="btn-primary whitespace-nowrap">Search</button>
          {search && (
            <button
              type="button"
              onClick={() => { setSearch(''); setSearchInput('') }}
              className="btn-ghost"
            >✕</button>
          )}
        </form>

        <select
          value={limit}
          onChange={e => setLimit(Number(e.target.value))}
          className="input w-auto bg-jarvis-bg text-sm"
        >
          {[20, 50, 100, 200].map(n => (
            <option key={n} value={n}>{n} rows</option>
          ))}
        </select>
      </div>

      {error && <p className="text-jarvis-red text-sm mb-3">{error}</p>}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-12 rounded bg-jarvis-border/20 animate-pulse" />
          ))}
        </div>
      ) : facts.length === 0 ? (
        <p className="text-jarvis-dim text-sm p-8 text-center">No facts found.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-jarvis-dim border-b border-jarvis-border">
                <th className="text-left py-2 pr-3 font-medium w-24">Domain</th>
                <th className="text-left py-2 pr-3 font-medium w-24">Type</th>
                <th className="text-left py-2 pr-3 font-medium">Summary</th>
                <th className="text-left py-2 pr-3 font-medium w-28">Confidence</th>
                <th className="text-left py-2 pr-3 font-medium w-24">Age</th>
              </tr>
            </thead>
            <tbody>
              {facts.map(fact => (
                <tr key={fact.id} className="border-b border-jarvis-border/40 hover:bg-white/5 transition-colors">
                  <td className="py-2 pr-3">
                    <span className="badge-idle capitalize">{fact.domain}</span>
                  </td>
                  <td className="py-2 pr-3 text-jarvis-dim">{fact.fact_type}</td>
                  <td className="py-2 pr-3 text-gray-300 leading-relaxed">
                    {(fact.summary || fact.content || '').slice(0, 120)}
                    {(fact.summary || fact.content || '').length > 120 && '…'}
                  </td>
                  <td className="py-2 pr-3">{confidenceBar(fact.confidence)}</td>
                  <td className="py-2 pr-3 text-jarvis-dim whitespace-nowrap">
                    {timeAgo(fact.created_at)}
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
