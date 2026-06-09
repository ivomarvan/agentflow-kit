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

    <!-- Input area — textarea is full width, both action buttons overlaid inside -->
    <div class="input-area">
      <div class="textarea-wrapper">
        <Textarea
          v-model="promptInput"
          :placeholder="isListening ? 'Listening…' : 'Type your message… (Enter to send, Shift+Enter for newline)'"
          :rows="2"
          :disabled="chatStore.isRunning"
          :class="['prompt-textarea', { listening: isListening }]"
          auto-resize
          @keydown.enter.exact.prevent="sendMessage"
        />
        <!-- Action buttons row — bottom-right of the textarea -->
        <div class="input-btns">
          <!-- Mic — only when STT is available -->
          <button
            v-if="sttAvailable"
            :class="['icon-btn', 'mic-btn', { active: isListening }]"
            :title="isListening ? 'Stop listening' : 'Speak your message'"
            :disabled="chatStore.isRunning && !isListening"
            type="button"
            @click="toggleListening"
          >
            <i :class="isListening ? 'pi pi-stop-circle' : 'pi pi-microphone'" />
          </button>

          <!-- Send -->
          <button
            :class="['icon-btn', 'send-btn', { running: chatStore.isRunning }]"
            :title="chatStore.isRunning ? 'Running…' : 'Send (Enter)'"
            :disabled="chatStore.isRunning || !promptInput.trim()"
            type="button"
            @click="sendMessage"
          >
            <i :class="chatStore.isRunning ? 'pi pi-spin pi-spinner' : 'pi pi-chevron-right'" />
          </button>
        </div>
      </div>
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
import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import { Textarea, Select } from 'primevue'
import MessageBubble from './MessageBubble.vue'
import EventLogPanel from './EventLogPanel.vue'
import { useChatStore } from '@/stores/chat'
import { useVoiceStore } from '@/stores/voice'
import { api } from '@/services/api'
import { connectEventStream, type WsMessage } from '@/services/wsClient'
import {
  isSpeechApiSupported,
  SpeechToText,
  TextToSpeech,
  GeminiTTS,
} from '@/services/speech'

interface SampleOption { label: string; value: string }

const chatStore  = useChatStore()
const voiceStore = useVoiceStore()

const promptInput   = ref('')
const samples       = ref<string[]>([])
const selectedSample = ref('')
const messagesEl    = ref<HTMLElement | null>(null)
const isListening   = ref(false)

const sttAvailable = ref(isSpeechApiSupported())
let stt: SpeechToText | null = null
const browserTts = new TextToSpeech()
const geminiTts  = new GeminiTTS()

const sampleOptions = computed<SampleOption[]>(() => [
  { label: '— type your own —', value: '' },
  ...samples.value.map(s => ({ label: s, value: s })),
])

onMounted(async () => {
  try { samples.value = await api.getSamples() } catch { samples.value = [] }
  if (sttAvailable.value) {
    stt = new SpeechToText(voiceStore.sttLang)
  }
})

onUnmounted(() => {
  stt?.stop()
  browserTts.stop()
  geminiTts.stop()
})

watch(() => voiceStore.sttLang, lang => stt?.setLang(lang))

watch(selectedSample, val => { promptInput.value = val })

watch(() => chatStore.messages.length, () => {
  nextTick(() => {
    messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight, behavior: 'smooth' })
  })
})

// ── STT ────────────────────────────────────────────────────────────

function toggleListening() {
  if (isListening.value) {
    stt?.stop()
    isListening.value = false
    return
  }
  if (!stt || chatStore.isRunning) return
  isListening.value = true

  stt.start(
    (result) => {
      // Final transcript: put in textarea
      promptInput.value = result.transcript
      isListening.value = false
      if (voiceStore.autoSend) sendMessage()
    },
    () => {
      // Recognition session ended (silence / timeout)
      isListening.value = false
    },
    (err) => {
      console.warn('STT error:', err)
      isListening.value = false
    },
    (interim) => {
      // Live preview: update textarea while user is speaking
      promptInput.value = interim
    },
  )
}

// ── Send & run ──────────────────────────────────────────────────────

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
        const result = (event.result as string) ?? 'Completed.'
        chatStore.completeMessage(msgId, result)
        chatStore.isRunning = false
        disconnect()
        if (voiceStore.ttsEnabled && result) {
          if (voiceStore.ttsBackend === 'gemini') {
            geminiTts.speak(result, voiceStore.geminiVoice, voiceStore.ttsLang).catch(
              err => console.warn('Gemini TTS error:', err)
            )
          } else {
            browserTts.speak(result, voiceStore.ttsVoiceName, voiceStore.ttsLang)
          }
        }
      } else if (event.type === 'run_error') {
        chatStore.errorMessage(msgId, (event.message as string) ?? 'Unknown error')
        chatStore.isRunning = false
        disconnect()
      }
    },
    () => { chatStore.isRunning = false },
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
.sample-select { flex: 1; min-width: 0; }

.input-area {
  display: flex;
}

/* Wrapper gives textarea a positioning context for the overlaid buttons */
.textarea-wrapper {
  position: relative;
  flex: 1;
}
.prompt-textarea {
  width: 100%;
  /* Reserve space for two icon buttons (mic + send) in bottom-right corner */
  padding-right: 4.6rem !important;
  transition: box-shadow 0.2s;
}
.prompt-textarea.listening {
  box-shadow: 0 0 0 2px #ef4444;
}

/* Row of action buttons — positioned in the bottom-right of the textarea */
.input-btns {
  position: absolute;
  right: 0.4rem;
  bottom: 0.4rem;
  display: flex;
  gap: 0.3rem;
  align-items: center;
  z-index: 1;
}

/* Shared circular button base */
.icon-btn {
  width: 1.9rem;
  height: 1.9rem;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.8rem;
  transition: opacity 0.15s, background 0.15s, box-shadow 0.15s;
  flex-shrink: 0;
}
.icon-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

/* Mic: neutral grey, red when active */
.mic-btn {
  background: var(--p-surface-200, #e2e8f0);
  color: var(--p-text-color, #334155);
  opacity: 0.7;
}
.mic-btn:hover:not(:disabled) {
  opacity: 1;
  background: var(--p-surface-300, #cbd5e1);
}
.mic-btn.active {
  background: #ef4444;
  color: #fff;
  opacity: 1;
  box-shadow: 0 0 0 3px #fca5a5;
}

/* Send: accent colour, prominent */
.send-btn {
  background: var(--p-primary-color, #6366f1);
  color: #fff;
  opacity: 0.85;
  font-size: 0.85rem;
}
.send-btn:hover:not(:disabled) {
  opacity: 1;
}
.send-btn.running {
  background: var(--p-surface-300, #cbd5e1);
  color: var(--p-text-color, #334155);
  opacity: 1;
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
.message.user {
  margin-right: 1.5rem;
  margin-left: 0;
}
.message.assistant {
  margin-left: 1.5rem;
  margin-right: 0;
}
.empty-state {
  text-align: center;
  color: var(--p-text-muted-color, #aaa);
  margin: auto;
}
</style>
