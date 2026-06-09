import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { WsMessage } from '@/services/wsClient'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  result: string | null
  isRunning: boolean
  events: WsMessage[]
  timestamp: Date
  run_id: string
}

/** A single line in the event log panel, shown below the chat. */
export interface LogLine {
  time: string     // HH:MM:SS
  tag: string      // uppercase label shown in the coloured badge
  text: string     // human-readable message
  level?: string   // 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' (for log events)
}

/** Format a WsMessage into a human-readable LogLine, or null to suppress it. */
function toLogLine(event: WsMessage): LogLine | null {
  const time = new Date().toLocaleTimeString('en-GB', { hour12: false })
  const type = event.type as string
  switch (type) {
    case 'question_sent':
      return { time, tag: 'USER', text: `Question: ${event.question as string}` }
    case 'step_start':
      return { time, tag: 'STEP', text: `→ ${event.vertex as string} (step ${event.step as number})` }
    case 'step_end':
      return { time, tag: 'STEP', text: `✓ ${event.vertex as string} → ${event.signal as string}` }
    case 'log':
      return {
        time, tag: (event.level as string) ?? 'LOG',
        text: event.message as string,
        level: (event.level as string)?.toUpperCase(),
      }
    case 'run_complete':
      return { time, tag: 'DONE', text: `Result: ${event.result as string ?? '(none)'}` }
    case 'run_error':
      return { time, tag: 'ERR', text: `Error: ${event.message as string}` }
    case 'ping':
    case 'pong':
      return null  // suppress heartbeats from the log
    default:
      return { time, tag: type.toUpperCase().slice(0, 6), text: JSON.stringify(event) }
  }
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const isRunning = ref(false)
  const eventLog = ref<LogLine[]>([])

  function addUserMessage(content: string): string {
    const id = crypto.randomUUID()
    messages.value.push({
      id,
      role: 'user',
      content,
      result: null,
      isRunning: false,
      events: [],
      timestamp: new Date(),
      run_id: '',
    })
    return id
  }

  function addAssistantMessage(runId: string): string {
    const id = crypto.randomUUID()
    messages.value.push({
      id,
      role: 'assistant',
      content: '',
      result: null,
      isRunning: true,
      events: [],
      timestamp: new Date(),
      run_id: runId,
    })
    return id
  }

  function appendEvent(msgId: string, event: WsMessage) {
    const msg = messages.value.find(m => m.id === msgId)
    if (msg) msg.events.push(event)
    const line = toLogLine(event)
    if (line) eventLog.value.push(line)
  }

  function completeMessage(msgId: string, result: string | null) {
    const msg = messages.value.find(m => m.id === msgId)
    if (msg) {
      msg.isRunning = false
      msg.result = result
    }
  }

  function errorMessage(msgId: string, error: string) {
    const msg = messages.value.find(m => m.id === msgId)
    if (msg) {
      msg.isRunning = false
      msg.result = `Error: ${error}`
    }
  }

  function clearLog() {
    eventLog.value = []
  }

  return {
    messages, isRunning, eventLog,
    addUserMessage, addAssistantMessage, appendEvent,
    completeMessage, errorMessage, clearLog,
  }
})
