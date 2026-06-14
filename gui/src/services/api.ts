const BASE = ''  // uses Vite proxy in dev; same origin in production

export interface AppInfo {
  /** Script stem (e.g. ``06_smart_home_assistant``) or class name fallback. */
  name: string
  /** Module docstring (Markdown) for the title tooltip. */
  doc: string
}

export interface LiveStateInfo {
  has_live_state: boolean
  display_schema?: Record<string, unknown>
  state_data?: Record<string, unknown>
}

export interface DemoToolSchema {
  name: string
  description: string
  parameters: {
    type: string
    properties: Record<string, JsonSchemaField>
    required?: string[]
  }
}

export interface JsonSchemaField {
  type?: string
  description?: string
  enum?: unknown[]
  minimum?: number
  maximum?: number
  default?: unknown
  'x-widget'?: string
}

export interface DemoActionResponse {
  result: string | null
  error: string | null
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

  getLiveState: (): Promise<LiveStateInfo> =>
    fetch(`${BASE}/api/live-state`).then(r => r.json()),

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

  getDemoTools: (): Promise<DemoToolSchema[]> =>
    fetch(`${BASE}/api/demo/tools`).then(async r => {
      if (!r.ok) {
        const data = await r.json()
        throw new Error((data as { error?: string }).error ?? 'Failed to load demo tools')
      }
      return r.json()
    }),

  callDemoAction: (toolName: string, params: Record<string, unknown>): Promise<DemoActionResponse> =>
    fetch(`${BASE}/api/demo/action/${encodeURIComponent(toolName)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }).then(async r => {
      const data = await r.json()
      if (!r.ok) {
        throw new Error((data as { detail?: string }).detail ?? 'Action failed')
      }
      return data
    }),
}
