const BASE = '/api'

export const api = {
  async health() {
    const r = await fetch(`${BASE}/health`)
    if (!r.ok) throw new Error('backend offline')
    return r.json()
  },

  async imageStatus() {
    const r = await fetch(`${BASE}/image/status`)
    return r.json()
  },

  async buildImage() {
    const r = await fetch(`${BASE}/image/build`, { method: 'POST' })
    if (!r.ok) throw new Error(await r.text())
    return r.json()
  },

  async listGroups() {
    const r = await fetch(`${BASE}/groups`)
    return r.json()
  },

  async getGroup(name) {
    const r = await fetch(`${BASE}/groups/${name}`)
    if (!r.ok) throw new Error(`Grupo '${name}' no encontrado`)
    return r.json()
  },

  async listServices() {
    const r = await fetch(`${BASE}/services`)
    return r.json()
  },

  async serviceStatus(name, port) {
    const r = await fetch(`${BASE}/services/${name}/status?port=${port}`)
    return r.json()
  },

  async startService(name, repo, port, secretsFile = null, envVars = null) {
    const r = await fetch(`${BASE}/services`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, repo, port, secrets_file: secretsFile, env_vars: envVars }),
    })
    if (!r.ok) {
      const err = await r.json().catch(() => ({ detail: r.statusText }))
      throw new Error(err.detail || r.statusText)
    }
    return r.json()
  },

  async stopAll() {
    const r = await fetch(`${BASE}/services`, { method: 'DELETE' })
    if (!r.ok) throw new Error(r.statusText)
    return r.json()
  },

  openEvalStream(group, level) {
    return new EventSource(`${BASE}/evaluate/${group}/${level}`)
  },
}
