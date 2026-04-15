import { useEffect, useState } from 'react'
import { api } from '../api'

export default function PreferencesPanel() {
  const [prefs, setPrefs] = useState(null)
  const [edited, setEdited] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  async function load() {
    try {
      const data = await api.preferences()
      setPrefs(data)
      setEdited(data)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { load() }, [])

  async function save() {
    setSaving(true)
    setSaved(false)
    try {
      const updated = await api.updatePreferences(edited)
      setPrefs(updated)
      setEdited(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
      setError(null)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  function set(key, value) {
    setEdited(prev => ({ ...prev, [key]: value }))
  }

  if (loading) return <p className="text-jarvis-dim text-sm p-4 animate-pulse">Loading preferences…</p>
  if (!prefs) return null

  return (
    <div className="max-w-2xl space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold text-gray-100">Preferences</h2>
          <p className="text-xs text-jarvis-dim">User preferences used by all specialists</p>
        </div>
        {saved && <span className="badge-success">✓ Saved</span>}
      </div>

      {error && <p className="text-jarvis-red text-sm">{error}</p>}

      <div className="card space-y-4">
        <Field label="City" hint="Format: City,US">
          <input
            className="input"
            value={edited.city ?? ''}
            onChange={e => set('city', e.target.value)}
          />
        </Field>

        <Field label="Monthly Budget ($)">
          <input
            className="input"
            type="number"
            min={0}
            step={10}
            value={edited.budget_monthly ?? 800}
            onChange={e => set('budget_monthly', parseFloat(e.target.value) || 0)}
          />
        </Field>

        <Field label="Notification Level">
          <select
            className="input bg-jarvis-bg"
            value={edited.notification_level ?? 'important'}
            onChange={e => set('notification_level', e.target.value)}
          >
            <option value="all">all</option>
            <option value="important">important</option>
            <option value="critical">critical</option>
          </select>
        </Field>

        <Field label="Weather in Brief">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              className="w-4 h-4 accent-blue-500"
              checked={edited.brief_include_weather !== false}
              onChange={e => set('brief_include_weather', e.target.checked)}
            />
            <span className="text-sm text-gray-300">Include weather summary in morning brief</span>
          </label>
        </Field>

        <Field label="Household Size">
          <input
            className="input"
            type="number"
            min={1}
            max={20}
            step={1}
            value={edited.household_size ?? 2}
            onChange={e => set('household_size', parseInt(e.target.value, 10) || 2)}
          />
        </Field>

        <Field label="Dietary Restrictions" hint="Comma-separated (e.g. vegetarian, gluten-free)">
          <input
            className="input"
            value={Array.isArray(edited.dietary_restrictions)
              ? edited.dietary_restrictions.join(', ')
              : (edited.dietary_restrictions ?? '')}
            onChange={e => set('dietary_restrictions',
              e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
          />
        </Field>

        <Field label="Investment Risk Tolerance">
          <select
            className="input bg-jarvis-bg"
            value={edited.investment_risk_tolerance ?? 'moderate'}
            onChange={e => set('investment_risk_tolerance', e.target.value)}
          >
            <option value="conservative">conservative</option>
            <option value="moderate">moderate</option>
            <option value="aggressive">aggressive</option>
          </select>
        </Field>
      </div>

      {/* Raw JSON viewer for advanced prefs */}
      <details className="card">
        <summary className="cursor-pointer text-sm text-jarvis-dim hover:text-gray-300 transition-colors">
          Advanced — all preferences (raw JSON)
        </summary>
        <div className="mt-3">
          <textarea
            className="input font-mono text-xs h-48 resize-y"
            value={JSON.stringify(edited, null, 2)}
            onChange={e => {
              try {
                setEdited(JSON.parse(e.target.value))
              } catch {
                // ignore parse errors while typing
              }
            }}
          />
        </div>
      </details>

      <div className="flex gap-2">
        <button
          onClick={save}
          disabled={saving}
          className={`btn-primary ${saving ? 'opacity-50 cursor-wait' : ''}`}
        >
          {saving ? 'Saving…' : 'Save Preferences'}
        </button>
        <button
          onClick={load}
          disabled={saving}
          className="btn-ghost"
        >
          Reset
        </button>
      </div>
    </div>
  )
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-300 mb-1">
        {label}
        {hint && <span className="ml-2 text-xs font-normal text-jarvis-dim">{hint}</span>}
      </label>
      {children}
    </div>
  )
}
