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

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([])
  const isRunning = ref(false)

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

  return { messages, isRunning, addUserMessage, addAssistantMessage, appendEvent, completeMessage, errorMessage }
})
