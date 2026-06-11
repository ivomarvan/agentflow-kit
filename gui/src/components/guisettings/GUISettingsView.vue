<template>
  <div class="gui-settings">

    <!-- ── Voice Input ──────────────────────────────────────────── -->
    <section class="settings-section">
      <h2 class="section-title">🎤 Voice Input (Speech → Text)</h2>

      <div v-if="!sttSupported" class="unsupported-notice">
        <i class="pi pi-exclamation-triangle" />
        Speech recognition is not supported in this browser.
        Use <strong>Chrome</strong> or <strong>Edge</strong> for full support.
      </div>

      <template v-else>
        <div class="setting-row">
          <label class="setting-label">
            Recognition language
            <span
              class="help-icon"
              v-tooltip.right="{
                value: 'Language you will speak in. The browser sends your audio to a cloud service (Google or Apple) for recognition. Choose the language you will speak — a mismatch causes poor results.',
                pt: { text: 'tt-text' }
              }"
            >?</span>
          </label>
          <Select
            v-model="voiceStore.sttLang"
            :options="[...STT_LANGUAGES]"
            option-label="label"
            option-value="code"
            class="setting-select"
          />
        </div>

        <div class="setting-row">
          <label class="setting-label">
            Auto-send after speech
            <span
              class="help-icon"
              v-tooltip.right="{
                value: 'When ON: recognised text is sent automatically — fastest for hands-free use.\nWhen OFF: the transcript appears in the text field first so you can review and edit before sending.',
                pt: { text: 'tt-text' }
              }"
            >?</span>
          </label>
          <div class="toggle-row">
            <ToggleSwitch v-model="voiceStore.autoSend" />
            <span class="toggle-hint">{{ voiceStore.autoSend ? 'Send immediately' : 'Edit before sending' }}</span>
          </div>
        </div>
      </template>
    </section>

    <hr class="divider" />

    <!-- ── Voice Output ─────────────────────────────────────────── -->
    <section class="settings-section">
      <h2 class="section-title">🔊 Voice Output (Text → Speech)</h2>

      <div v-if="!ttsSupported" class="unsupported-notice">
        <i class="pi pi-exclamation-triangle" />
        Speech synthesis is not supported in this browser.
      </div>

      <template v-else>
        <div class="setting-row">
          <label class="setting-label">
            Speak responses
            <span
              class="help-icon"
              v-tooltip.right="{
                value: 'When ON: the agent\'s answer is read aloud after every reply.\nWhen OFF: responses appear as text only — no audio output.',
                pt: { text: 'tt-text' }
              }"
            >?</span>
          </label>
          <div class="toggle-row">
            <ToggleSwitch v-model="voiceStore.ttsEnabled" />
            <span class="toggle-hint">{{ voiceStore.ttsEnabled ? 'Responses read aloud' : 'Text only (silent)' }}</span>
          </div>
        </div>

        <template v-if="voiceStore.ttsEnabled">

          <!-- TTS engine selector -->
          <div class="setting-row">
            <label class="setting-label">
              Engine
              <span
                class="help-icon"
                v-tooltip.right="{
                  value: 'Browser: uses built-in OS voices — no internet needed, quality depends on installed voices.\nGemini: uses Google\'s Gemini TTS model via the server proxy — high quality, supports Czech and 75+ languages, requires GEMINI_API_KEY.',
                  pt: { text: 'tt-text' }
                }"
              >?</span>
            </label>
            <SelectButton
              v-model="voiceStore.ttsBackend"
              :options="backendOptions"
              option-label="label"
              option-value="value"
            />
          </div>

          <!-- Output language (shared for both backends) -->
          <div class="setting-row">
            <label class="setting-label">
              Output language
              <span
                class="help-icon"
                v-tooltip.right="{
                  value: 'Language used for speech synthesis. Should match the language of the agent\'s responses.',
                  pt: { text: 'tt-text' }
                }"
              >?</span>
            </label>
            <Select
              v-model="voiceStore.ttsLang"
              :options="[...STT_LANGUAGES]"
              option-label="label"
              option-value="code"
              class="setting-select"
              @change="voiceStore.ttsVoiceName = null"
            />
          </div>

          <!-- Browser TTS voice selector -->
          <template v-if="voiceStore.ttsBackend === 'browser'">
            <div class="setting-row">
              <label class="setting-label">
                Voice
                <span
                  class="help-icon"
                  v-tooltip.right="{
                    value: 'Voice used for speech synthesis. Voices marked ★ are online (higher quality, require internet). Offline voices work without network. The list depends on your OS and browser.',
                    pt: { text: 'tt-text' }
                  }"
                >?</span>
              </label>
              <div class="voice-select-wrap">
                <Select
                  v-model="voiceStore.ttsVoiceName"
                  :options="browserVoiceOptions"
                  option-label="label"
                  option-value="value"
                  placeholder="— browser default —"
                  class="setting-select"
                  :show-clear="true"
                  :disabled="browserVoiceOptions.length === 0 && !voicesLoading"
                />
                <span v-if="voicesLoading" class="loading-hint">Loading voices…</span>
                <span v-else-if="browserVoiceOptions.length === 0" class="loading-hint warn">
                  No specific voices found for this language. The browser will use
                  its default voice. Install additional voices via your OS
                  language/speech settings, or switch to the Gemini engine.
                </span>
              </div>
            </div>
          </template>

          <!-- Gemini TTS voice selector -->
          <template v-else>
            <div class="setting-row">
              <label class="setting-label">
                Gemini voice
                <span
                  class="help-icon"
                  v-tooltip.right="{
                    value: 'Pre-built Gemini voice. All voices work across all languages — choose by sound character. Try the Test button to preview.',
                    pt: { text: 'tt-text' }
                  }"
                >?</span>
              </label>
              <Select
                v-model="voiceStore.geminiVoice"
                :options="GEMINI_VOICES"
                option-label="label"
                option-value="name"
                class="setting-select"
              />
            </div>
          </template>

          <div class="setting-row">
            <label class="setting-label" />
            <button class="test-btn" @click="testTts" :disabled="isTesting">
              <i :class="isTesting ? 'pi pi-spin pi-spinner' : 'pi pi-volume-up'" />
              Test voice
            </button>
          </div>
        </template>
      </template>
    </section>

  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Select, ToggleSwitch, SelectButton } from 'primevue'
import { useVoiceStore } from '@/stores/voice'
import {
  STT_LANGUAGES,
  TextToSpeech,
  GeminiTTS,
  GEMINI_VOICES,
  isSpeechApiSupported,
  isTtsSupported,
  getTestSentence,
} from '@/services/speech'

const voiceStore = useVoiceStore()
const sttSupported = ref(isSpeechApiSupported())
const ttsSupported = ref(isTtsSupported())
const browserTts = new TextToSpeech()
const geminiTts = new GeminiTTS()
const voicesRaw = ref<SpeechSynthesisVoice[]>([])
const voicesLoading = ref(true)
const isTesting = ref(false)

const backendOptions = [
  { label: 'Browser (OS voices)', value: 'browser' },
  { label: 'Gemini TTS ✨', value: 'gemini' },
]

interface VoiceOption { label: string; value: string }

const browserVoiceOptions = computed<VoiceOption[]>(() => {
  // voicesRaw must be read here so Vue tracks it as a reactive dependency.
  // Without it the computed would not re-run when voices load asynchronously.
  void voicesRaw.value
  const lang = voiceStore.ttsLang
  return browserTts.getVoicesForLang(lang).map(v => ({
    label: v.localService ? v.name : `★ ${v.name}`,
    value: v.name,
  }))
})

function loadVoices() {
  voicesRaw.value = window.speechSynthesis?.getVoices() ?? []
  voicesLoading.value = voicesRaw.value.length === 0
}

onMounted(() => {
  loadVoices()
  if ('speechSynthesis' in window) {
    window.speechSynthesis.onvoiceschanged = () => {
      loadVoices()
      voicesLoading.value = false
    }
    // Some browsers populate voices synchronously
    if (window.speechSynthesis.getVoices().length > 0) voicesLoading.value = false
  }
})

async function testTts() {
  isTesting.value = true
  const lang = voiceStore.ttsLang
  const sentence = getTestSentence(lang)
  try {
    if (voiceStore.ttsBackend === 'gemini') {
      await geminiTts.speak(sentence, voiceStore.geminiVoice, lang)
    } else {
      browserTts.speak(sentence, voiceStore.ttsVoiceName, lang)
    }
  } catch (err) {
    console.error('TTS test failed:', err)
  } finally {
    setTimeout(() => { isTesting.value = false }, 2500)
  }
}
</script>

<style scoped>
.gui-settings {
  padding: 1rem 0.5rem;
  max-width: 600px;
}
.settings-section {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.section-title {
  font-size: 1rem;
  font-weight: 600;
  margin: 0 0 0.25rem;
  color: var(--p-text-color, #1e293b);
}
.divider {
  border: none;
  border-top: 1px solid var(--p-content-border-color, #e2e8f0);
  margin: 1.25rem 0;
}
.setting-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  flex-wrap: wrap;
}
.setting-label {
  width: 180px;
  flex-shrink: 0;
  font-size: 0.875rem;
  color: var(--p-text-color, #334155);
  display: flex;
  align-items: center;
  gap: 0.3rem;
}
.setting-select {
  flex: 1;
  min-width: 180px;
}
.help-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.1rem;
  height: 1.1rem;
  border-radius: 50%;
  background: var(--p-surface-200, #e2e8f0);
  color: var(--p-text-muted-color, #64748b);
  font-size: 0.7rem;
  font-weight: 700;
  cursor: help;
  flex-shrink: 0;
}
.toggle-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.toggle-hint {
  font-size: 0.8rem;
  color: var(--p-text-muted-color, #888);
}
.voice-select-wrap {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  flex: 1;
}
.loading-hint {
  font-size: 0.75rem;
  color: var(--p-text-muted-color, #888);
  font-style: italic;
}
.loading-hint.warn {
  color: #92400e;
  font-style: normal;
}
.test-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.9rem;
  border: 1px solid var(--p-content-border-color, #cbd5e1);
  border-radius: 6px;
  background: var(--p-surface-0, #fff);
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--p-text-color, #334155);
  transition: background 0.15s;
}
.test-btn:hover:not(:disabled) { background: var(--p-surface-100, #f1f5f9); }
.test-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.unsupported-notice {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.6rem 0.9rem;
  background: var(--p-surface-100, #fef9c3);
  border: 1px solid #fcd34d;
  border-radius: 6px;
  font-size: 0.85rem;
  color: #92400e;
}
</style>
