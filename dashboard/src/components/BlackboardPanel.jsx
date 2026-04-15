import { useEffect, useState } from 'react'
import { api } from '../api'

const URGENCY_CLASS = {
  urgent: 'badge-failure',
  high:   'badge-warning',
  normal: 'badge-idle',
  low:    'badge-idle',
}

const URGENCY_ICON = {
  urgent: '🚨',
  high:   '⚠️',
  normal: 'ℹ️',
  low:    '💬',
}

const TOPICS = ['', 'alerts', 'requests', 'updates', 'recommendations']

function timeAgo(iso) {
  if (!iso) return '—'
  const diff = (Date.now() - new Date(iso)) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

export default function BlackboardPanel() {
  const [posts, setPosts] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [topic, setTopic] = useState('')

  async function refresh() {
    setLoading(true)
    try {
      const data = await api.blackboard(topic || undefined)
      setPosts(data.posts)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { refresh() }, [topic])

  // Auto-refresh every 15s
  useEffect(() => {
    const id = setInterval(refresh, 15_000)
    return () => clearInterval(id)
  }, [topic])

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Specialist Blackboard</h2>
          <p className="text-xs text-jarvis-dim">Cross-specialist signals and alerts</p>
        </div>
        <button onClick={refresh} className="btn-ghost text-xs">↻ refresh</button>
      </div>

      <div className="flex gap-2 mb-3">
        <select
          value={topic}
          onChange={e => setTopic(e.target.value)}
          className="input w-auto bg-jarvis-bg text-sm"
        >
          <option value="">All topics</option>
          {TOPICS.filter(Boolean).map(t => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>

      {error && <p className="text-jarvis-red text-sm mb-3">{error}</p>}

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-16 rounded bg-jarvis-border/20 animate-pulse" />
          ))}
        </div>
      ) : posts.length === 0 ? (
        <p className="text-jarvis-dim text-sm p-8 text-center">
          No blackboard posts. Specialists will post here when they have signals to share.
        </p>
      ) : (
        <div className="space-y-2">
          {posts.map((post, i) => (
            <div key={post.id ?? i} className="card flex gap-3">
              <span className="text-lg shrink-0">{URGENCY_ICON[post.urgency] || 'ℹ️'}</span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-xs text-jarvis-accent">{post.agent}</span>
                  <span className={URGENCY_CLASS[post.urgency] ?? 'badge-idle'}>
                    {post.urgency}
                  </span>
                  {post.topic && (
                    <span className="text-xs text-jarvis-dim">#{post.topic}</span>
                  )}
                  <span className="text-xs text-jarvis-dim ml-auto">
                    {timeAgo(post.posted_at)}
                  </span>
                </div>
                <p className="text-sm text-gray-300 leading-relaxed">{post.content}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
