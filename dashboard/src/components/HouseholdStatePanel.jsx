import { useEffect, useState } from 'react'
import { api } from '../api'

const PRIMARY_ICONS = {
  normal:          '🏡',
  summer:          '☀️',
  winter:          '❄️',
  holiday:         '🎄',
  budget_tight:    '💸',
  guests_coming:   '👥',
  vacation:        '✈️',
  sick_day:        '🤧',
  spring_cleaning: '🧹',
}

const MODIFIER_ICONS = {
  grocery_day:          '🛒',
  payday:               '💰',
  date_night:           '🌙',
  meal_prep:            '🍳',
  leftovers:            '🥡',
  school_night:         '📚',
  weekend:              '🎉',
  long_weekend:         '🎊',
  outdoor_dining:       '🌿',
  guests_arriving_soon: '🚗',
  cooking_ahead:        '👨‍🍳',
  low_pantry:           '📦',
}

function timeAgo(iso) {
  if (!iso) return '—'
  const diff = (Date.now() - new Date(iso)) / 1000
  if (diff < 60) return `${Math.round(diff)}s ago`
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`
  return `${Math.round(diff / 86400)}d ago`
}

export default function HouseholdStatePanel() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [saving, setSaving] = useState(false)
  const [reason, setReason] = useState('')

  async function refresh() {
    try {
      const d = await api.householdState()
      setData(d)
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

  async function transition(value) {
    setSaving(true)
    try {
      await api.updateHouseholdState('transition', value, reason || 'dashboard update')
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function toggleModifier(mod, active) {
    setSaving(true)
    try {
      await api.updateHouseholdState(
        active ? 'remove_modifier' : 'add_modifier',
        mod,
        reason || 'dashboard update',
      )
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="text-jarvis-dim text-sm p-4 animate-pulse">Loading state…</p>
  if (error) return <p className="text-jarvis-red text-sm p-4">{error}</p>
  if (!data) return null

  const { current, history, valid_primaries, valid_modifiers } = data
  const activeModifiers = new Set(current.modifiers)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Household State</h2>
          <p className="text-xs text-jarvis-dim">State machine controls</p>
        </div>
        <button onClick={refresh} className="btn-ghost text-xs">↻ refresh</button>
      </div>

      {/* Current state banner */}
      <div className="card flex items-center gap-4 border-jarvis-accent/40">
        <span className="text-4xl">{PRIMARY_ICONS[current.primary] || '🏠'}</span>
        <div>
          <div className="text-lg font-semibold text-jarvis-accent capitalize">
            {current.primary.replace(/_/g, ' ')}
          </div>
          <div className="flex flex-wrap gap-1 mt-1">
            {current.modifiers.length === 0
              ? <span className="text-xs text-jarvis-dim">no active modifiers</span>
              : current.modifiers.map(m => (
                  <span key={m} className="badge-warning capitalize">
                    {MODIFIER_ICONS[m]} {m.replace(/_/g, ' ')}
                  </span>
                ))
            }
          </div>
        </div>
      </div>

      {/* Reason input */}
      <div>
        <label className="text-xs text-jarvis-dim block mb-1">Reason for change (optional)</label>
        <input
          className="input"
          placeholder="e.g. heading out for vacation…"
          value={reason}
          onChange={e => setReason(e.target.value)}
          disabled={saving}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Primary state */}
        <div className="card">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Primary State</h3>
          <div className="grid grid-cols-2 gap-2">
            {valid_primaries.map(p => (
              <button
                key={p}
                onClick={() => transition(p)}
                disabled={saving || p === current.primary}
                className={`
                  text-left px-3 py-2 rounded text-xs font-medium transition-colors flex items-center gap-2
                  ${p === current.primary
                    ? 'bg-jarvis-accent/20 text-jarvis-accent border border-jarvis-accent/40 cursor-default'
                    : 'border border-jarvis-border text-jarvis-dim hover:text-gray-200 hover:border-gray-500'}
                  ${saving ? 'opacity-50 cursor-wait' : ''}
                `}
              >
                <span>{PRIMARY_ICONS[p] || '•'}</span>
                <span className="capitalize">{p.replace(/_/g, ' ')}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Modifiers */}
        <div className="card">
          <h3 className="text-sm font-medium text-gray-300 mb-3">Modifiers</h3>
          <div className="grid grid-cols-2 gap-2">
            {valid_modifiers.map(m => {
              const active = activeModifiers.has(m)
              return (
                <button
                  key={m}
                  onClick={() => toggleModifier(m, active)}
                  disabled={saving}
                  className={`
                    text-left px-3 py-2 rounded text-xs font-medium transition-colors flex items-center gap-2
                    ${active
                      ? 'bg-yellow-900/40 text-yellow-400 border border-yellow-700'
                      : 'border border-jarvis-border text-jarvis-dim hover:text-gray-200 hover:border-gray-500'}
                    ${saving ? 'opacity-50 cursor-wait' : ''}
                  `}
                >
                  <span>{MODIFIER_ICONS[m] || '•'}</span>
                  <span className="capitalize">{m.replace(/_/g, ' ')}</span>
                </button>
              )
            })}
          </div>
        </div>
      </div>

      {/* Transition history */}
      {history.length > 0 && (
        <div className="card">
          <h3 className="text-sm font-medium text-gray-300 mb-2">Recent Transitions</h3>
          <div className="space-y-1">
            {history.slice(0, 8).map((h, i) => (
              <div key={h.id ?? i} className="flex items-start gap-3 text-xs">
                <span className="text-jarvis-dim whitespace-nowrap w-16 shrink-0">
                  {timeAgo(h.timestamp)}
                </span>
                <span className="text-jarvis-accent capitalize">{h.event?.replace(/_/g, ' ')}</span>
                <span className="text-gray-300">
                  {h.from && h.to ? `${h.from} → ${h.to}` : h.to || h.from || ''}
                </span>
                {h.reason && (
                  <span className="text-jarvis-dim italic truncate">{h.reason}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
