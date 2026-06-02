const BASE = ''  // uses Vite proxy in dev; same origin in production

export interface AppInfo {
  /** Script stem (e.g. ``06_smart_home_assistant``) or class name fallback. */
  name: string
  /** Module docstring (Markdown) for the title tooltip. */
  doc: string
}

export interface RunResponse {
  run_id: string
  status: 'started' | 'conflict'
}

export const api = {
  getInfo: (): Promise<AppInfo> =>
    fetch(`${BASE}/api/info`).then(r => r.json()),

  getSamples: (): Promise<string[]> =>
    fetch(`${BASE}/api/samples`).then(r => r.json()),

  /** Interactive graph HTML (same as CLI ``graph --browser``). */
  getGraph: (): Promise<string> =>
    fetch(`${BASE}/api/graph`).then(r => r.text()),

  getSchema: (): Promise<Record<string, unknown>> =>
    fetch(`${BASE}/api/schema`).then(r => r.json()),

  getConfig: (): Promise<Record<string, unknown>> =>
    fetch(`${BASE}/api/config`).then(r => r.json()),

  setConfig: (path: string, value: unknown): Promise<void> =>
    fetch(`${BASE}/api/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, value }),
    }).then(() => {}),

  startRun: (prompt: string): Promise<{ run_id: string; status: string; detail?: string }> =>
    fetch(`${BASE}/api/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    }).then(async r => {
      const data = await r.json()
      if (!r.ok) return { run_id: '', status: 'conflict', detail: data.detail }
      return data
    }),
}
