export interface WsMessage {
  type: string
  run_id?: string
  event_type?: string
  [key: string]: unknown
}

export function connectEventStream(
  runId: string,
  onMessage: (msg: WsMessage) => void,
  onClose?: () => void,
): () => void {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  const ws = new WebSocket(`${protocol}//${host}/ws/${runId}`)

  ws.onmessage = (e) => {
    try {
      onMessage(JSON.parse(e.data))
    } catch {
      // ignore parse errors
    }
  }
  ws.onclose = () => onClose?.()
  ws.onerror = (e) => console.warn('WS error', e)

  return () => ws.close()
}
