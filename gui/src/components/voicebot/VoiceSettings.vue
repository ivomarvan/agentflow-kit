<template>
  <div class="voice-settings">
    <div class="setting-row">
      <label>Language:</label>
      <Select
        v-model="selectedLang"
        :options="[...STT_LANGUAGES]"
        option-label="label"
        option-value="code"
        placeholder="Select language"
        @change="emit('update:lang', selectedLang)"
      />
    </div>
    <div class="setting-row">
      <label>Voice:</label>
      <Select
        v-model="selectedVoice"
        :options="voices"
        option-label="name"
        placeholder="Default"
        @change="emit('update:voice', selectedVoice)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Select } from 'primevue'
import { STT_LANGUAGES, TextToSpeech } from '@/services/speech'

const props = defineProps<{
  lang: string
  voice: SpeechSynthesisVoice | null
}>()

const emit = defineEmits<{
  (e: 'update:lang', v: string): void
  (e: 'update:voice', v: SpeechSynthesisVoice | null): void
}>()

const selectedLang = ref(props.lang)
const selectedVoice = ref<SpeechSynthesisVoice | null>(props.voice)
const voices = ref<SpeechSynthesisVoice[]>([])

const tts = new TextToSpeech()

onMounted(() => {
  // Voices load asynchronously in some browsers
  voices.value = tts.getVoices()
  window.speechSynthesis.onvoiceschanged = () => {
    voices.value = tts.getVoices()
  }
})
</script>

<style scoped>
.voice-settings { display: flex; gap: 1rem; flex-wrap: wrap; align-items: center; }
.setting-row { display: flex; align-items: center; gap: 0.5rem; }
label { font-size: 0.85rem; color: var(--p-text-muted-color, #666); }
</style>
