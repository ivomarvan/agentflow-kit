<template>
  <div class="chat-view">
    <!-- Sample prompts -->
    <div v-if="sampleOptions.length > 1" class="sample-prompts">
      <label for="sample-select" class="label">Try:</label>
      <Select
        id="sample-select"
        v-model="selectedSample"
        :options="sampleOptions"
        option-label="label"
        option-value="value"
        placeholder="— type your own —"
        class="sample-select"
      />
    </div>

    <!-- Input (above conversation history) -->
    <div class="input-area">
      <Textarea
        v-model="promptInput"
        placeholder="Type your message… (Enter to send, Shift+Enter for newline)"
        :rows="3"
        :disabled="chatStore.isRunning"
        @keydown.enter.exact.prevent="sendMessage"
        class="prompt-textarea"
        auto-resize
      />
      <Button
        label="Send"
        icon="pi pi-send"
        :disabled="chatStore.isRunning || !promptInput.trim()"
        :loading="chatStore.isRunning"
        @click="sendMessage"
      />
    </div>

    <!-- Conversation history -->
    <div class="messages" ref="messagesEl">
      <div
        v-for="msg in chatStore.messages"
        :key="msg.id"
        :class="['message', msg.role]"
      >
        <MessageBubble :message="msg" />
      </div>
      <div v-if="chatStore.messages.length === 0" class="empty-state">
        <p>Send a message to start a conversation.</p>
      </div>
    </div>

    <!-- Event log panel -->
    <EventLogPanel />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch, computed } from 'vue'
import { Button, Textarea, Select } from 'primevue'
import MessageBubble from './MessageBubble.vue'
import EventLogPanel from './EventLogPanel.vue'
import { useChatStore } from '@/stores/chat'
import { api } from '@/services/api'
import { connectEventStream, type WsMessage } from '@/services/wsClient'

interface SampleOption {
  label: string
  value: string
}

const chatStore = useChatStore()
const promptInput = ref('')
const samples = ref<string[]>([])
const selectedSample = ref('')
const messagesEl = ref<HTMLElement | null>(null)

const sampleOptions = computed<SampleOption[]>(() => [
  { label: '— type your own —', value: '' },
  ...samples.value.map((s) => ({ label: s, value: s })),
])

onMounted(async () => {
  try {
    samples.value = await api.getSamples()
  } catch {
    samples.value = []
  }
})

watch(selectedSample, (val) => {
  promptInput.value = val
})

watch(() => chatStore.messages.length, () => {
  nextTick(() => {
    messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight, behavior: 'smooth' })
  })
})

async function sendMessage() {
  const text = promptInput.value.trim()
  if (!text || chatStore.isRunning) return
  promptInput.value = ''
  selectedSample.value = ''
  chatStore.isRunning = true
  chatStore.addUserMessage(text)
  const response = await api.startRun(text)
  if (response.status === 'conflict' || !response.run_id) {
    chatStore.isRunning = false
    return
  }
  const msgId = chatStore.addAssistantMessage(response.run_id)
  const disconnect = connectEventStream(
    response.run_id,
    (event: WsMessage) => {
      chatStore.appendEvent(msgId, event)
      if (event.type === 'run_complete') {
        chatStore.completeMessage(msgId, (event.result as string) ?? 'Completed.')
        chatStore.isRunning = false
        disconnect()
      } else if (event.type === 'run_error') {
        chatStore.errorMessage(msgId, (event.message as string) ?? 'Unknown error')
        chatStore.isRunning = false
        disconnect()
      }
    },
    () => {
      chatStore.isRunning = false
    },
  )
}
</script>

<style scoped>
.chat-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  height: calc(100vh - 160px);
}
.sample-prompts {
  display: flex;
  gap: 0.75rem;
  align-items: center;
}
.sample-prompts .label {
  font-size: 0.85rem;
  color: var(--p-text-muted-color, #888);
  flex-shrink: 0;
}
.sample-select {
  flex: 1;
  min-width: 0;
}
.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  padding: 0.5rem;
  border: 1px solid var(--p-content-border-color, #e2e8f0);
  border-radius: 8px;
}
.message.user { align-self: flex-end; }
.message.assistant { align-self: flex-start; width: 100%; }
.empty-state {
  text-align: center;
  color: var(--p-text-muted-color, #aaa);
  margin: auto;
}
.input-area {
  display: flex;
  gap: 0.5rem;
  align-items: flex-end;
}
.prompt-textarea { flex: 1; }
</style>
