<template>
  <div class="chat-view">
    <!-- Sample prompts -->
    <div v-if="samples.length" class="sample-prompts">
      <span class="label">Try:</span>
      <Button
        v-for="s in samples"
        :key="s"
        :label="s"
        size="small"
        severity="secondary"
        @click="promptInput = s"
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

    <!-- Input -->
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
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { Button, Textarea } from 'primevue'
import MessageBubble from './MessageBubble.vue'
import { useChatStore } from '@/stores/chat'
import { api } from '@/services/api'
import { connectEventStream, type WsMessage } from '@/services/wsClient'

const chatStore = useChatStore()
const promptInput = ref('')
const samples = ref<string[]>([])
const messagesEl = ref<HTMLElement | null>(null)

onMounted(async () => {
  try {
    samples.value = await api.getSamples()
  } catch {
    samples.value = []
  }
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
  flex-wrap: wrap;
  gap: 0.5rem;
  align-items: center;
}
.sample-prompts .label {
  font-size: 0.85rem;
  color: var(--p-text-muted-color, #888);
}
.messages {
  flex: 1;
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
