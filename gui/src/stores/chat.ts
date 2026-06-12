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

/** A single line in the event log panel. */
export interface LogLine {
  time: string      // HH:MM:SS
  tag: string       // uppercase label shown in the coloured badge
  text: string      // human-readable one-liner
  level?: string    // 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' (for log events)
  detail?: unknown  // structured data shown in the details panel (no truncation)
  seq: number       // sequential number within current run (resets on new question)
  isStats?: boolean // true for the RunStats summary block
}

/** Format a WsMessage into a human-readable LogLine, or null to suppress it. */
function toLogLine(event: WsMessage, seq: number): LogLine | null {
  const time = new Date().toLocaleTimeString('en-GB', { hour12: false })
  const type = event.type as string

  switch (type) {
    case 'question_sent':
      return {
        time, tag: 'USER',
        text: `Question: ${event.question as string}`,
        detail: { event_type: 'question_sent', question: event.question },
        seq,
      }

    case 'step_start':
      return {
        time, tag: 'STEP',
        text: `→ ${event.vertex as string} (step ${event.step as number})`,
        detail: { event_type: 'step_start', vertex: event.vertex, step: event.step, input_state: event.detail },
        seq,
      }

    case 'step_end': {
      const fromCache = event.from_cache as boolean | undefined
      const cacheFlag = fromCache ? ' ⚡cache' : ''
      return {
        time, tag: 'STEP',
        text: `✓ ${event.vertex as string}${cacheFlag} → ${event.signal as string}`,
        detail: { event_type: 'step_end', vertex: event.vertex, step: event.step, signal: event.signal, from_cache: fromCache, output_patch: event.detail },
        seq,
      }
    }

    case 'tool_call': {
      const inputs = event.inputs as Record<string, unknown> | undefined
      const output = event.output as string ?? ''
      return {
        time, tag: 'TOOL',
        text: `⚙ ${event.tool_name as string}(${Object.keys(inputs ?? {}).join(', ')})`,
        detail: { event_type: 'tool_call', tool_name: event.tool_name, step: event.step, inputs: inputs ?? {}, output },
        seq,
      }
    }

    case 'llm_call': {
      const model = event.model as string
      const messages = event.messages as Array<Record<string, unknown>>
      const tools = event.tools as Array<unknown> | null | undefined
      const temperature = (event.temperature as number) ?? 0.2
      return {
        time, tag: 'LLM',
        text: `⬆ ${model} (${messages.length} msgs${tools?.length ? `, tools: ${tools.length}` : ''})`,
        detail: { event_type: 'llm_call', model, temperature, messages, tools: tools ?? null },
        seq,
      }
    }

    case 'llm_response': {
      const model = event.model as string
      const content = event.content as string | null
      const toolCalls = event.tool_calls as Array<Record<string, unknown>> | null
      const usage = event.usage as Record<string, number> | null
      const fromCache = (event.from_cache as boolean) ?? false
      const preview = content
        ? content.slice(0, 80).replace(/\n/g, ' ') + (content.length > 80 ? '…' : '')
        : (toolCalls?.length
            ? `tool_calls: ${toolCalls.map(t => t.name).join(', ')}`
            : '(empty)')
      return {
        time, tag: 'LLM',
        text: `⬇ ${model}${fromCache ? ' ⚡' : ''}: ${preview}`,
        detail: { event_type: 'llm_response', model, from_cache: fromCache, usage, content, tool_calls: toolCalls },
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
      const totalCalls = llmCalls + cacheHits
      const cacheStr = totalCalls > 0 ? `Cache: ${cacheHits}/${totalCalls}` : 'Cache: —'
      return {
        time, tag: 'STAT',
        text: `Elapsed ${elapsedSec}s · tokens ${total.toLocaleString()} · ${cacheStr}`,
        detail: {
          event_type: 'run_stats',
          elapsed_s: parseFloat(elapsedSec),
          total_tokens: total,
          prompt_tokens: (event.prompt_tokens as number) ?? 0,
          completion_tokens: (event.completion_tokens as number) ?? 0,
          llm_calls: llmCalls,
          cache_hits: cacheHits,
          by_model: event.by_model,
        },
        seq,
        isStats: true,
      }
    }

    case 'log':
      return {
        time, tag: (event.level as string) ?? 'LOG',
        text: event.message as string,
        level: (event.level as string)?.toUpperCase(),
        detail: { event_type: 'log', level: event.level, message: event.message, logger: event.logger_name },
        seq,
      }

    case 'run_complete':
      return {
        time, tag: 'DONE',
        text: `Result: ${(event.result as string) ?? '(none)'}`,
        detail: { event_type: 'run_complete', result: event.result },
        seq,
      }

    case 'run_error':
      return {
        time, tag: 'ERR',
        text: `Error: ${event.message as string}`,
        detail: { event_type: 'run_error', message: event.message },
        seq,
      }

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
