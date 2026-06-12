<template>
  <div class="chat-view-root">

    <!-- Splitter is rendered only once, after hasLiveState is resolved from the API.
         Rendering it before we know the panel count causes PrimeVue to change the
         number of SplitterPanels mid-render, which breaks size distribution. -->
    <Splitter v-if="splitterReady" layout="vertical" class="chat-splitter">

      <!-- ── TOP PANEL: conversation history + input ── -->
      <SplitterPanel :size="hasLiveState ? 45 : 65" :minSize="20" class="chat-pane chat-top-pane">
        <div class="chat-pane-inner">

          <!-- Panel header — consistent style with Event Log -->
          <div class="pane-header">
            <span
              class="pane-title"
              v-tooltip.right="{
                value: 'Conversation history — all questions and answers in this session. ' +
                       'Enter to send, Shift+Enter for a new line.',
                showDelay: 400
              }"
            >💬 Conversation</span>
          </div>

          <!-- Content area below the header -->
          <div class="chat-pane-content">

            <!-- Input area — placed above messages for a question-first layout -->
            <div class="input-area">
              <div class="textarea-wrapper">
                <Textarea
                  v-model="promptInput"
                  :placeholder="isListening ? 'Listening…' : 'Select or Say or Type your message… (Enter to send, Shift+Enter for newline)'"
                  :rows="2"
                  :disabled="chatStore.isRunning"
                  :class="['prompt-textarea', { listening: isListening }, `btns-${inputBtnsCount}`]"
                  auto-resize
                  @keydown.enter.exact.prevent="sendMessage"
                />
                <div class="input-btns">
                  <!-- Sample prompts dropdown — only when samples are available -->
                  <button
                    v-if="hasSamples"
                    class="icon-btn samples-btn"
                    title="Sample prompts — click to pick a pre-made question"
                    type="button"
                    @click="toggleSamplesMenu"
                  >
                    <i class="pi pi-list" />
                  </button>

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
                Send a message to start a conversation.
              </div>
            </div>

          </div><!-- .chat-pane-content -->

        </div>
      </SplitterPanel>

      <!-- ── MIDDLE PANEL: live agent state (only for apps with live_state) ── -->
      <SplitterPanel v-if="hasLiveState" :size="20" :minSize="8" class="chat-pane chat-mid-pane">
        <StateViewerPanel />
      </SplitterPanel>

      <!-- ── BOTTOM PANEL: event log ── -->
      <SplitterPanel :size="hasLiveState ? 35 : 35" :minSize="12" class="chat-pane chat-bottom-pane">
        <EventLogPanel />
      </SplitterPanel>

    </Splitter>

    <!-- Placeholder while the live-state API call is in flight (avoids layout flash) -->
    <div v-else class="chat-splitter" />

    <!-- Sample prompts popover (teleported to body by PrimeVue) -->
    <Popover ref="samplesPopover">
      <ul class="samples-list">
        <li
          v-for="sample in samples"
          :key="sample"
          class="samples-list-item"
          @click="selectSample(sample)"
        >
          {{ sample }}
        </li>
      </ul>
    </Popover>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch, computed } from 'vue'
import { Textarea, Popover, Splitter, SplitterPanel } from 'primevue'
import MessageBubble from './MessageBubble.vue'
import EventLogPanel from './EventLogPanel.vue'
import StateViewerPanel from '@/components/stateviewer/StateViewerPanel.vue'
import { useChatStore } from '@/stores/chat'
import { useVoiceStore } from '@/stores/voice'
import { useStateViewerStore } from '@/stores/stateViewer'
import { api } from '@/services/api'
import { connectEventStream, type WsMessage } from '@/services/wsClient'
import {
  isSpeechApiSupported,
  SpeechToText,
  TextToSpeech,
  GeminiTTS,
} from '@/services/speech'

const chatStore  = useChatStore()
const voiceStore = useVoiceStore()
const svStore    = useStateViewerStore()

/** True when the current agent has a live_state model → show middle pane. */
const hasLiveState = computed(() => svStore.hasLiveStateCapability)

/** Deferred to true after getLiveState() resolves so Splitter renders once with the correct panel count. */
const splitterReady = ref(false)

const promptInput    = ref('')
const samples        = ref<string[]>([])
const messagesEl     = ref<HTMLElement | null>(null)
const isListening    = ref(false)
const samplesPopover = ref()

const sttAvailable = ref(isSpeechApiSupported())
let stt: SpeechToText | null = null
const browserTts = new TextToSpeech()
const geminiTts  = new GeminiTTS()

const hasSamples = computed(() => samples.value.length > 0)

/** Number of visible action buttons — drives textarea padding-right class. */
const inputBtnsCount = computed(() =>
  1 + (sttAvailable.value ? 1 : 0) + (hasSamples.value ? 1 : 0)
)

onMounted(async () => {
  try { samples.value = await api.getSamples() } catch { samples.value = [] }
  if (sttAvailable.value) {
    stt = new SpeechToText(voiceStore.sttLang)
  }
  // Pre-populate Live State panel with the agent's initial state (if any).
  // splitterReady is set AFTER this resolves so the Splitter is rendered once
  // with the correct panel count (2 or 3), preventing mid-render panel insertion.
  try {
    const liveStateData = await api.getLiveState()
    if (liveStateData.has_live_state && liveStateData.display_schema && liveStateData.state_data) {
      svStore.initFromApi(
        liveStateData.display_schema as Parameters<typeof svStore.initFromApi>[0],
        liveStateData.state_data,
      )
    }
  } catch { /* agent without live state — ignore */ }
  splitterReady.value = true
})

onUnmounted(() => {
  stt?.stop()
  browserTts.stop()
  geminiTts.stop()
})

watch(() => voiceStore.sttLang, lang => stt?.setLang(lang))

watch(() => chatStore.messages.length, () => {
  nextTick(() => {
    messagesEl.value?.scrollTo({ top: messagesEl.value.scrollHeight, behavior: 'smooth' })
  })
})

// ── Sample prompts popover ──────────────────────────────────────────

function toggleSamplesMenu(event: MouseEvent) {
  samplesPopover.value?.toggle(event)
}

function selectSample(sample: string) {
  promptInput.value = sample
  samplesPopover.value?.hide()
}

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
      promptInput.value = result.transcript
      isListening.value = false
      if (voiceStore.autoSend) sendMessage()
    },
    () => {
      isListening.value = false
    },
    (err) => {
      console.warn('STT error:', err)
      isListening.value = false
    },
    (interim) => {
      promptInput.value = interim
    },
  )
}

// ── Send & run ──────────────────────────────────────────────────────

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
  let statsWaitTimer: ReturnType<typeof setTimeout> | null = null
  const disconnect = connectEventStream(
    response.run_id,
    (event: WsMessage) => {
      chatStore.appendEvent(msgId, event)
      if (event.type === 'run_complete') {
        const result = (event.result as string) ?? 'Completed.'
        if (event.is_error) {
          chatStore.errorMessage(msgId, result)
        } else {
          chatStore.completeMessage(msgId, result)
        }
        chatStore.isRunning = false
        // Delay disconnect so run_stats (emitted just after run_complete) can arrive.
        statsWaitTimer = setTimeout(disconnect, 2000)
        if (voiceStore.ttsEnabled && result) {
          if (voiceStore.ttsBackend === 'gemini') {
            geminiTts.speak(result, voiceStore.geminiVoice, voiceStore.ttsLang).catch(
              err => console.warn('Gemini TTS error:', err)
            )
          } else {
            browserTts.speak(result, voiceStore.ttsVoiceName, voiceStore.ttsLang)
          }
        }
      } else if (event.type === 'run_stats') {
        if (statsWaitTimer !== null) { clearTimeout(statsWaitTimer); statsWaitTimer = null }
        disconnect()
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
.chat-view-root {
  /* Thin wrapper so Popover teleport doesn't break layout */
}

.chat-splitter {
  height: calc(100vh - 130px);
  min-height: 400px;
}

/* Both panels need overflow:hidden so the inner scroll works correctly */
.chat-pane {
  overflow: hidden;
}

/* Inner flex layout for the top panel — no outer border, header provides visual anchor */
.chat-pane-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  background: transparent;
}

/* Panel header — consistent style with Event Log, no rounded corners (no outer frame) */
.pane-header {
  display: flex;
  align-items: center;
  padding: 0.25rem 0.6rem;
  border-bottom: 1px solid var(--p-content-border-color, #e2e8f0);
  background: var(--p-surface-section, #f1f5f9);
  flex-shrink: 0;
}
.pane-title {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-text-muted-color, #888);
  cursor: default;
}

/* Scrollable content area below the header */
.chat-pane-content {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  padding: 0.4rem 0.5rem;
  gap: 0.4rem;
  box-sizing: border-box;
  overflow: hidden;
  background: var(--p-surface-card, #fff);
}

/* ── Messages ─────────────────────────────────────────────────────── */

.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  padding: 0.3rem 0.4rem;
}
.empty-state {
  color: var(--p-text-muted-color, #aaa);
  font-style: italic;
  margin: auto;
  text-align: center;
  font-size: 0.85rem;
}

/* ── Input area ───────────────────────────────────────────────────── */

.input-area {
  display: flex;
  flex-shrink: 0;
}

/* Wrapper gives textarea a positioning context for the overlaid buttons */
.textarea-wrapper {
  position: relative;
  flex: 1;
}
.prompt-textarea {
  width: 100%;
  /* Default: send button only; btns-N classes widen the right gutter */
  padding-right: 2.8rem !important;
  transition: box-shadow 0.2s;
}
.prompt-textarea.btns-2 { padding-right: 4.6rem !important; }
.prompt-textarea.btns-3 { padding-right: 6.8rem !important; }
.prompt-textarea.listening {
  box-shadow: 0 0 0 2px #ef4444;
}

/* Row of action buttons — vertically centred on the right edge of the textarea */
.input-btns {
  position: absolute;
  right: 0.4rem;
  top: 50%;
  transform: translateY(-50%);
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

/* Samples: neutral grey */
.samples-btn {
  background: var(--p-surface-200, #e2e8f0);
  color: var(--p-text-color, #334155);
  opacity: 0.7;
}
.samples-btn:hover:not(:disabled) {
  opacity: 1;
  background: var(--p-surface-300, #cbd5e1);
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

/* Sample prompts popover list */
.samples-list {
  list-style: none;
  margin: 0;
  padding: 0.25rem 0;
  max-width: min(28rem, 80vw);
  max-height: 20rem;
  overflow-y: auto;
}
.samples-list-item {
  padding: 0.45rem 0.9rem;
  cursor: pointer;
  border-radius: 4px;
  font-size: 0.875rem;
  line-height: 1.4;
  color: var(--p-text-color, #334155);
}
.samples-list-item:hover {
  background: var(--p-primary-50, #eef2ff);
  color: var(--p-primary-color, #6366f1);
}
</style>
