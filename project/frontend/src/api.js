// Thin wrapper around fetch(); always throws Error with a readable message.
function formatDetail(detail) {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(d => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ')
  return JSON.stringify(detail)
}

async function request(path, options = {}) {
  let res
  try {
    res = await fetch('/api' + path, { headers: { 'Content-Type': 'application/json' }, ...options })
  } catch {
    throw new Error('Cannot reach the backend. Make sure FastAPI is running on port 8000.')
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try { msg = formatDetail((await res.json()).detail) || msg } catch { /* ignore */ }
    throw new Error(msg)
  }
  return res.status === 204 ? null : res.json()
}

const send = (method, body) => ({ method, body: JSON.stringify(body) })

export const api = {
  defaultTopology: () => request('/default-topology'),
  scenarios: () => request('/scenarios'),
  simulate: body => request('/simulate', send('POST', body)),
  compare: body => request('/compare', send('POST', body)),
  topologies: () => request('/topologies'),
  topology: id => request(`/topologies/${id}`),
  saveTopology: body => request('/topologies', send('POST', body)),
  updateTopology: (id, body) => request(`/topologies/${id}`, send('PUT', body)),
  deleteTopology: id => request(`/topologies/${id}`, { method: 'DELETE' }),
  runs: () => request('/runs'),
  run: id => request(`/runs/${id}`),
}
