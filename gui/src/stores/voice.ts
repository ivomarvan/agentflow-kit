/**
 * Pinia store for voice (STT + TTS) settings.
 * All values are persisted to localStorage so they survive page reloads.
 */

import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { detectBrowserLang } from '@/services/speech'

const LS_KEY = 'agentflow.voiceSettings'

/** Which TTS engine to use for speaking agent responses. */
export type TtsBackend = 'browser' | 'gemini'

interface Persisted {
  sttLang: string
  ttsLang: string
  ttsVoiceName: string | null   // browser TTS voice name
  ttsEnabled: boolean
  autoSend: boolean
  ttsBackend: TtsBackend
  geminiVoice: string           // Gemini pre-built voice name
}

function load(): Partial<Persisted> {
  try {
    const raw = localStorage.getItem(LS_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function save(data: Persisted): void {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(data))
  } catch { /* quota exceeded or private mode */ }
}

export const useVoiceStore = defineStore('voice', () => {
  const saved = load()
  const browserLang = detectBrowserLang()

  const sttLang      = ref<string>(saved.sttLang      ?? browserLang)
  const ttsLang      = ref<string>(saved.ttsLang      ?? browserLang)
  const ttsVoiceName = ref<string | null>(saved.ttsVoiceName ?? null)
  const ttsEnabled   = ref<boolean>(saved.ttsEnabled   ?? true)
  /** When true, STT result is sent immediately. When false, text lands in textarea for review. */
  const autoSend     = ref<boolean>(saved.autoSend     ?? false)
  /** Which TTS engine to use: 'browser' (built-in OS voices) or 'gemini' (cloud, high quality). */
  const ttsBackend   = ref<TtsBackend>(saved.ttsBackend ?? 'browser')
  /** Gemini pre-built voice name used when ttsBackend === 'gemini'. */
  const geminiVoice  = ref<string>(saved.geminiVoice  ?? 'Kore')

  function persist() {
    save({
      sttLang: sttLang.value,
      ttsLang: ttsLang.value,
      ttsVoiceName: ttsVoiceName.value,
      ttsEnabled: ttsEnabled.value,
      autoSend: autoSend.value,
      ttsBackend: ttsBackend.value,
      geminiVoice: geminiVoice.value,
    })
  }

  watch([sttLang, ttsLang, ttsVoiceName, ttsEnabled, autoSend, ttsBackend, geminiVoice], persist)

  return { sttLang, ttsLang, ttsVoiceName, ttsEnabled, autoSend, ttsBackend, geminiVoice }
})
