/**
 * Jarvis API client — all calls are relative so they work both in dev
 * (proxied via Vite to 192.168.111.28:8000) and in production (same origin).
 */

const BASE = ''

async function get(path) {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

async function put(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export const api = {
  // System
  status:        () => get('/api/status'),
  adapters:      () => get('/api/adapters'),

  // Specialists
  specialists:   () => get('/api/specialists'),

  // Knowledge Lake
  knowledgeLake: (params = {}) => {
    const qs = new URLSearchParams()
    if (params.domain)    qs.set('domain', params.domain)
    if (params.fact_type) qs.set('fact_type', params.fact_type)
    if (params.q)         qs.set('q', params.q)
    if (params.limit)     qs.set('limit', params.limit)
    return get(`/api/knowledge-lake?${qs}`)
  },

  // Decisions
  decisions:       (params = {}) => {
    const qs = new URLSearchParams()
    if (params.agent)      qs.set('agent', params.agent)
    if (params.capability) qs.set('capability', params.capability)
    if (params.limit)      qs.set('limit', params.limit)
    return get(`/api/decisions?${qs}`)
  },
  recentDecisions: (n = 50) => get(`/api/decisions/recent?n=${n}`),

  // Household state
  householdState:       () => get('/api/household-state'),
  updateHouseholdState: (action, value, reason) =>
    put('/api/household-state', { action, value, reason }),

  // Preferences
  preferences:       () => get('/api/preferences'),
  updatePreferences: (updates) => post('/api/preferences', updates),

  // Engines
  enginesStatus: () => get('/api/engines/status'),

  // Blackboard
  blackboard: (topic) => {
    const qs = topic ? `?topic=${encodeURIComponent(topic)}` : ''
    return get(`/api/blackboard${qs}`)
  },

  // Workflows
  workflows: () => get('/api/workflows'),
}
