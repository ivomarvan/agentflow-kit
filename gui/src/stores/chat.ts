import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { WsMessage } from '@/services/wsClient'
import { useStateViewerStore } from '@/stores/stateViewer'

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
  detail?: string  // tooltip content (newline-separated key: value pairs)
  seq: number      // sequential number within current run (resets on new question)
  isStats?: boolean  // true for the RunStats summary block
}

/** Format detail dict into a readable tooltip string. */
function formatDetail(detail: Record<string, string> | undefined): string | undefined {
  if (!detail || Object.keys(detail).length === 0) return undefined
  return Object.entries(detail)
    .map(([k, v]) => `${k}: ${v}`)
    .join('\n')
}

/** Format per-model token stats into a readable multiline string. */
function formatByModel(byModel: Record<string, Record<string, number>>): string {
  return Object.entries(byModel)
    .map(([model, m]) => `  ${model}: prompt=${m.prompt?.toLocaleString() ?? 0}  completion=${m.completion?.toLocaleString() ?? 0}  (${m.calls ?? 0} calls)`)
    .join('\n')
}

/** Format a WsMessage into a human-readable LogLine, or null to suppress it. */
function toLogLine(event: WsMessage, seq: number): LogLine | null {
  const time = new Date().toLocaleTimeString('en-GB', { hour12: false })
  const type = event.type as string

  switch (type) {
    case 'question_sent':
      return { time, tag: 'USER', text: `Question: ${event.question as string}`, seq }

    case 'step_start': {
      const detail = formatDetail(event.detail as Record<string, string> | undefined)
      return {
        time, tag: 'STEP',
        text: `→ ${event.vertex as string} (step ${event.step as number})`,
        detail,
        seq,
      }
    }

    case 'step_end': {
      const detail = formatDetail(event.detail as Record<string, string> | undefined)
      const fromCache = event.from_cache as boolean | undefined
      const cacheFlag = fromCache ? ' ⚡cache' : ''
      return {
        time, tag: 'STEP',
        text: `✓ ${event.vertex as string}${cacheFlag} → ${event.signal as string}`,
        detail,
        seq,
      }
    }

    case 'tool_call': {
      const inputs = event.inputs as Record<string, string> | undefined
      const output = event.output as string ?? ''
      const detail = [
        inputs && Object.keys(inputs).length ? 'inputs:\n' + Object.entries(inputs).map(([k, v]) => `  ${k}: ${v}`).join('\n') : null,
        output ? `output:\n  ${output}` : null,
      ].filter(Boolean).join('\n')
      return {
        time, tag: 'TOOL',
        text: `⚙ ${event.tool_name as string}(${Object.keys(inputs ?? {}).join(', ')})`,
        detail: detail || undefined,
        seq,
      }
    }

    case 'state_update':
      return null  // shown in StateViewerPanel — not in event log

    case 'run_stats': {
      const elapsedSec = ((event.elapsed_ms as number) / 1000).toFixed(1)
      const total = (event.total_tokens as number) ?? 0
      const llmCalls = (event.llm_calls as number) ?? 0
      const cacheHits = (event.cache_hits as number) ?? 0
      const byModel = event.by_model as Record<string, Record<string, number>> | undefined
      const byModelStr = byModel && Object.keys(byModel).length ? formatByModel(byModel) : null
      const totalCalls = llmCalls + cacheHits
      const cacheStr = totalCalls > 0 ? `Cache: ${cacheHits}/${totalCalls}` : 'Cache: —'
      const summaryLines = [
        `Time: ${elapsedSec}s`,
        total > 0 ? `Tokens: ${total.toLocaleString()} (prompt=${(event.prompt_tokens as number)?.toLocaleString() ?? 0}, completion=${(event.completion_tokens as number)?.toLocaleString() ?? 0})` : null,
        byModelStr ? `Per model:\n${byModelStr}` : null,
        cacheStr,
      ].filter(Boolean).join('\n')
      return {
        time, tag: 'STAT', text: `Elapsed ${elapsedSec}s · tokens ${total.toLocaleString()} · ${cacheStr}`,
        detail: summaryLines,
        seq,
        isStats: true,
      }
    }

    case 'log':
      return {
        time, tag: (event.level as string) ?? 'LOG',
        text: event.message as string,
        level: (event.level as string)?.toUpperCase(),
        seq,
      }

    case 'run_complete':
      return { time, tag: 'DONE', text: `Result: ${event.result as string ?? '(none)'}`, seq }

    case 'run_error':
      return { time, tag: 'ERR', text: `Error: ${event.message as string}`, seq }

    case 'ping':
    case 'pong':
      return null  // suppress heartbeats from the log

    default:
      return { time, tag: type.toUpperCase().slice(0, 6), text: JSON.stringify(event), seq }
  }
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const isRunning = ref(false)
  const eventLog = ref<LogLine[]>([])
  // Sequential counter reset on each new question
  let _runSeq = 0

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

    // Forward live state updates to the state viewer store
    if ((event.type as string) === 'state_update') {
      useStateViewerStore().handleStateUpdate(event as Record<string, unknown>)
    }

    // Reset the run sequence counter at the start of each new question
    if ((event.type as string) === 'question_sent') {
      _runSeq = 0
    }

    _runSeq++
    const line = toLogLine(event, _runSeq)
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
    _runSeq = 0
  }

  return {
    messages, isRunning, eventLog,
    addUserMessage, addAssistantMessage, appendEvent,
    completeMessage, errorMessage, clearLog,
  }
})
