import { useEffect, useState } from 'react'
import { api } from '../api'

const DOMAIN_ICONS = {
  grocery:  '🛒',
  finance:  '💰',
  calendar: '📅',
  home:     '🏠',
  news:     '📰',
  investor: '📈',
}

function outcomeClass(outcome) {
  if (!outcome) return 'badge-idle'
  if (outcome === 'success') return 'badge-success'
  if (outcome === 'failure') return 'badge-failure'
  return 'badge-warning'
}

function timeAgo(iso) {
  if (!iso) return null
  const diff = (Date.now() - new Date(iso)) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

export default function SpecialistsPanel() {
  const [specialists, setSpecialists] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  async function refresh() {
    try {
      const data = await api.specialists()
      setSpecialists(data.specialists)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 30_000)
    return () => clearInterval(id)
  }, [])

  if (loading) return <Loading />
  if (error) return <ErrorMsg msg={error} />

  return (
    <div>
      <SectionHeader title="Specialists" subtitle="6 domain agents" onRefresh={refresh} />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {specialists.map(spec => (
          <SpecialistCard key={spec.name} spec={spec} />
        ))}
      </div>
    </div>
  )
}

function SpecialistCard({ spec }) {
  const ago = timeAgo(spec.last_run)
  return (
    <div className="card flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">{DOMAIN_ICONS[spec.domain] || '🤖'}</span>
          <div>
            <div className="text-sm font-medium text-gray-200">{spec.domain}</div>
            <div className="text-xs text-jarvis-dim">{spec.name}</div>
          </div>
        </div>
        <span className={outcomeClass(spec.last_outcome)}>
          {spec.last_outcome ?? 'idle'}
        </span>
      </div>

      {spec.last_decision && (
        <p className="text-xs text-jarvis-dim leading-relaxed border-t border-jarvis-border pt-2 line-clamp-2">
          {spec.last_decision}
        </p>
      )}

      <div className="flex items-center justify-between text-xs text-jarvis-dim mt-auto pt-2 border-t border-jarvis-border">
        <span title={spec.schedule}>⏱ {spec.schedule}</span>
        <span>{ago ? `ran ${ago}` : 'never run'}</span>
      </div>
    </div>
  )
}

function Loading() {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="card h-28 animate-pulse bg-jarvis-border/20" />
      ))}
    </div>
  )
}

function ErrorMsg({ msg }) {
  return <p className="text-jarvis-red text-sm p-4">{msg}</p>
}

function SectionHeader({ title, subtitle, onRefresh }) {
  return (
    <div className="flex items-center justify-between mb-3">
      <div>
        <h2 className="text-base font-semibold text-gray-100">{title}</h2>
        {subtitle && <p className="text-xs text-jarvis-dim">{subtitle}</p>}
      </div>
      <button onClick={onRefresh} className="btn-ghost text-xs">↻ refresh</button>
    </div>
  )
}
