<template>
  <div class="voicebot-view">
    <!-- Browser support warning -->
    <Message v-if="!speechSupported" severity="warn">
      VoiceBot requires Chrome or Edge (Web Speech API).
    </Message>

    <template v-else>
      <!-- Settings row -->
      <VoiceSettings
        v-model:lang="sttLang"
        v-model:voice="ttsVoice"
        class="settings-row"
      />

      <!-- Conversation (shared with Chat tab) -->
      <div class="messages" ref="messagesEl">
        <div
          v-for="msg in chatStore.messages"
          :key="msg.id"
          :class="['message', msg.role]"
        >
          <MessageBubble :message="msg" />
        </div>
        <div v-if="chatStore.messages.length === 0" class="empty-state">
          Press the microphone button to speak.
        </div>
      </div>

      <!-- Transcript preview -->
      <div v-if="transcript" class="transcript">
        <i class="pi pi-microphone" /> <em>{{ transcript }}</em>
      </div>

      <!-- Mic button -->
      <div class="controls">
        <Button
          :icon="isListening ? 'pi pi-stop-circle' : 'pi pi-microphone'"
          :severity="isListening ? 'danger' : 'primary'"
          :label="isListening ? 'Stop' : 'Speak'"
          size="large"
          :disabled="chatStore.isRunning"
          :loading="chatStore.isRunning"
          rounded
          @click="toggleListening"
        />
        <span v-if="statusText" class="status-text">{{ statusText }}</span>
      </div>

      <!-- Event log panel -->
      <EventLogPanel />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { Button, Message } from 'primevue'
import MessageBubble from '@/components/chat/MessageBubble.vue'
import EventLogPanel from '@/components/chat/EventLogPanel.vue'
import VoiceSettings from './VoiceSettings.vue'
import { useChatStore } from '@/stores/chat'
import { api } from '@/services/api'
import { connectEventStream } from '@/services/wsClient'
import {
  isSpeechApiSupported,
  SpeechToText,
  TextToSpeech,
  STT_LANGUAGES,
} from '@/services/speech'

const chatStore = useChatStore()
const speechSupported = ref(isSpeechApiSupported())
const sttLang = ref(STT_LANGUAGES[0].code)  // cs-CZ
const ttsVoice = ref<SpeechSynthesisVoice | null>(null)
const isListening = ref(false)
const transcript = ref('')
const statusText = ref('')
const messagesEl = ref<HTMLElement | null>(null)

let stt: SpeechToText | null = null
const tts = new TextToSpeech()

onMounted(() => {
  if (speechSupported.value) {
    stt = new SpeechToText(sttLang.value)
  }
})

watch(sttLang, (lang) => {
  stt?.setLang(lang)
})

watch(() => chatStore.messages.length, () => {
  nextTick(() => {
    messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight, behavior: 'smooth' })
  })
})

function toggleListening() {
  if (isListening.value) {
    stt?.stop()
    isListening.value = false
    statusText.value = ''
  } else {
    startListening()
  }
}

function startListening() {
  if (!stt || chatStore.isRunning) return
  isListening.value = true
  statusText.value = 'Listening…'
  transcript.value = ''
  stt.start(
    (result) => {
      transcript.value = result.transcript
      isListening.value = false
      statusText.value = ''
      sendMessage(result.transcript)
    },
    () => {
      isListening.value = false
      if (!transcript.value) statusText.value = 'No speech detected.'
    },
    (err) => {
      isListening.value = false
      statusText.value = `Error: ${err}`
    },
  )
}

async function sendMessage(text: string) {
  if (!text.trim() || chatStore.isRunning) return
  chatStore.isRunning = true
  chatStore.addUserMessage(text)
  transcript.value = ''

  const response = await api.startRun(text)
  if (response.status === 'conflict' || !response.run_id) {
    chatStore.isRunning = false
    return
  }

  const msgId = chatStore.addAssistantMessage(response.run_id)
  const disconnect = connectEventStream(
    response.run_id,
    (event) => {
      chatStore.appendEvent(msgId, event)
      if (event.type === 'run_complete') {
        const result = (event.result as string) ?? 'Completed.'
        chatStore.completeMessage(msgId, result)
        chatStore.isRunning = false
        disconnect()
        // Speak the assistant's response aloud
        tts.speak(result, ttsVoice.value, sttLang.value)
      } else if (event.type === 'run_error') {
        chatStore.errorMessage(msgId, (event.message as string) ?? 'Error')
        chatStore.isRunning = false
        disconnect()
      }
    },
    () => { chatStore.isRunning = false },
  )
}
</script>

<style scoped>
.voicebot-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
  height: calc(100vh - 160px);
}
.settings-row { flex-shrink: 0; }
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
.transcript {
  font-style: italic;
  color: var(--p-text-muted-color, #888);
  font-size: 0.9rem;
  padding: 0.25rem 0.5rem;
}
.controls {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  padding: 0.5rem;
}
.status-text { font-size: 0.85rem; color: var(--p-text-muted-color, #888); }
.empty-state {
  text-align: center;
  color: var(--p-text-muted-color, #aaa);
  margin: auto;
}
</style>
