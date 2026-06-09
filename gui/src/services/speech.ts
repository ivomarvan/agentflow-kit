/**
 * Thin wrappers around Web Speech API (STT + browser TTS) and Gemini TTS proxy.
 * STT works in Chrome and Safari; browser TTS in all modern browsers.
 * Caller should check isSpeechApiSupported() before using SpeechToText.
 */

export function isSpeechApiSupported(): boolean {
  return (
    'SpeechRecognition' in window ||
    'webkitSpeechRecognition' in window
  )
}

export function isTtsSupported(): boolean {
  return 'speechSynthesis' in window
}

export interface SpeechRecognitionResult {
  transcript: string
  confidence: number
}

export class SpeechToText {
  // Typed as any — SpeechRecognition is a webkit-prefixed API not always in TS DOM lib
  private recognition: any

  constructor(lang = 'en-US') {
    const SR =
      (window as any).SpeechRecognition ??
      (window as any).webkitSpeechRecognition
    this.recognition = new SR()
    this.recognition.lang = lang
    this.recognition.continuous = false
    this.recognition.interimResults = true  // needed for live textarea preview
  }

  setLang(lang: string): void {
    this.recognition.lang = lang
  }

  /**
   * Start recognition.
   * @param onResult  Called once with the final transcript.
   * @param onEnd     Called when the recognition session ends (with or without result).
   * @param onError   Called on recognition error.
   * @param onInterim Called on each interim (partial) result — use for live textarea preview.
   */
  start(
    onResult: (result: SpeechRecognitionResult) => void,
    onEnd: () => void,
    onError: (err: string) => void,
    onInterim?: (transcript: string) => void,
  ): void {
    let finalSent = false
    this.recognition.onresult = (e: any) => {
      let interimText = ''
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i]
        if (r.isFinal) {
          finalSent = true
          onResult({ transcript: r[0].transcript, confidence: r[0].confidence })
        } else {
          interimText += r[0].transcript
        }
      }
      if (interimText && onInterim) onInterim(interimText)
    }
    this.recognition.onend = () => {
      if (!finalSent && onInterim) onInterim('')  // clear preview on silent end
      onEnd()
    }
    this.recognition.onerror = (e: any) => onError(e.error)
    this.recognition.start()
  }

  stop(): void {
    try { this.recognition.stop() } catch { /* already stopped */ }
  }
}

export class TextToSpeech {
  speak(text: string, voiceName: string | null, lang: string): void {
    window.speechSynthesis.cancel()
    const utt = new SpeechSynthesisUtterance(text)
    utt.lang = lang
    if (voiceName) {
      const voices = window.speechSynthesis.getVoices()
      const match = voices.find(v => v.name === voiceName && v.lang.startsWith(lang.slice(0, 2)))
        ?? voices.find(v => v.name === voiceName)
      if (match) utt.voice = match
    }
    window.speechSynthesis.speak(utt)
  }

  stop(): void {
    window.speechSynthesis.cancel()
  }

  /** Returns voices filtered to the given BCP-47 language prefix, sorted: online first. */
  getVoicesForLang(lang: string): SpeechSynthesisVoice[] {
    const prefix = lang.slice(0, 2).toLowerCase()
    return window.speechSynthesis
      .getVoices()
      .filter(v => v.lang.toLowerCase().startsWith(prefix))
      .sort((a, b) => (a.localService ? 1 : 0) - (b.localService ? 1 : 0))
  }
}

/** Broad list of BCP-47 tags supported by Chrome / Safari STT. */
export const STT_LANGUAGES = [
  { code: 'cs-CZ', label: 'Čeština' },
  { code: 'sk-SK', label: 'Slovenčina' },
  { code: 'en-US', label: 'English (US)' },
  { code: 'en-GB', label: 'English (UK)' },
  { code: 'en-AU', label: 'English (AU)' },
  { code: 'de-DE', label: 'Deutsch' },
  { code: 'de-AT', label: 'Deutsch (Österreich)' },
  { code: 'fr-FR', label: 'Français' },
  { code: 'es-ES', label: 'Español (España)' },
  { code: 'es-MX', label: 'Español (México)' },
  { code: 'it-IT', label: 'Italiano' },
  { code: 'pt-PT', label: 'Português (Portugal)' },
  { code: 'pt-BR', label: 'Português (Brasil)' },
  { code: 'nl-NL', label: 'Nederlands' },
  { code: 'pl-PL', label: 'Polski' },
  { code: 'hu-HU', label: 'Magyar' },
  { code: 'ro-RO', label: 'Română' },
  { code: 'sv-SE', label: 'Svenska' },
  { code: 'nb-NO', label: 'Norsk (Bokmål)' },
  { code: 'da-DK', label: 'Dansk' },
  { code: 'fi-FI', label: 'Suomi' },
  { code: 'uk-UA', label: 'Українська' },
  { code: 'ru-RU', label: 'Русский' },
  { code: 'ja-JP', label: '日本語' },
  { code: 'zh-CN', label: '中文 (简体)' },
  { code: 'zh-TW', label: '中文 (繁體)' },
  { code: 'ko-KR', label: '한국어' },
  { code: 'ar-SA', label: 'العربية' },
  { code: 'tr-TR', label: 'Türkçe' },
  { code: 'he-IL', label: 'עברית' },
] as const

export type SttLanguageCode = typeof STT_LANGUAGES[number]['code']

/** Short native-language sentence used in the "Test voice" button in Settings. */
export const TTS_TEST_SENTENCES: Readonly<Record<string, string>> = {
  'cs-CZ': 'Toto je zkouška hlasového výstupu.',
  'sk-SK': 'Toto je skúška hlasového výstupu.',
  'en-US': 'This is a voice output test.',
  'en-GB': 'This is a voice output test.',
  'en-AU': 'This is a voice output test.',
  'de-DE': 'Dies ist ein Test der Sprachausgabe.',
  'de-AT': 'Dies ist ein Test der Sprachausgabe.',
  'fr-FR': "Ceci est un test de la sortie vocale.",
  'es-ES': 'Esta es una prueba de salida de voz.',
  'es-MX': 'Esta es una prueba de salida de voz.',
  'it-IT': 'Questo è un test dell\'uscita vocale.',
  'pt-PT': 'Este é um teste de saída de voz.',
  'pt-BR': 'Este é um teste de saída de voz.',
  'nl-NL': 'Dit is een test van de spraakuitvoer.',
  'pl-PL': 'To jest test wyjścia głosowego.',
  'hu-HU': 'Ez egy hangkimeneti teszt.',
  'ro-RO': 'Acesta este un test de ieșire vocală.',
  'sv-SE': 'Det här är ett test av röstutmatning.',
  'nb-NO': 'Dette er en test av taleutgang.',
  'da-DK': 'Dette er en test af stemmeudsendelse.',
  'fi-FI': 'Tämä on äänitulosteen testi.',
  'uk-UA': 'Це тест голосового виводу.',
  'ru-RU': 'Это тест голосового вывода.',
  'ja-JP': 'これは音声出力のテストです。',
  'zh-CN': '这是语音输出测试。',
  'zh-TW': '這是語音輸出測試。',
  'ko-KR': '이것은 음성 출력 테스트입니다.',
  'ar-SA': 'هذا اختبار للإخراج الصوتي.',
  'tr-TR': 'Bu bir ses çıkışı testidir.',
  'he-IL': 'זהו בדיקת פלט קולי.',
} as const

/**
 * Returns the native-language test sentence for the given BCP-47 language tag.
 * Falls back to English if the language is not in the map.
 */
export function getTestSentence(lang: string): string {
  return TTS_TEST_SENTENCES[lang] ?? TTS_TEST_SENTENCES['en-US']
}

/** Detect the best matching STT language from the browser locale. */
export function detectBrowserLang(): string {
  const raw = navigator.language ?? 'en-US'
  const exact = STT_LANGUAGES.find(l => l.code === raw)
  if (exact) return exact.code
  const prefix = raw.slice(0, 2).toLowerCase()
  const partial = STT_LANGUAGES.find(l => l.code.toLowerCase().startsWith(prefix))
  return partial?.code ?? 'en-US'
}

// ---------------------------------------------------------------------------
// Gemini TTS (server-side proxy with file cache)
// ---------------------------------------------------------------------------

export interface GeminiVoice {
  name: string
  label: string
}

/**
 * Hardcoded voice list (mirrors GEMINI_VOICES in tts_service.py).
 * Loaded eagerly to avoid a round-trip when the Settings tab first opens.
 */
export const GEMINI_VOICES: GeminiVoice[] = [
  { name: 'Aoede',    label: 'Aoede' },
  { name: 'Charon',   label: 'Charon' },
  { name: 'Fenrir',   label: 'Fenrir' },
  { name: 'Kore',     label: 'Kore' },
  { name: 'Leda',     label: 'Leda' },
  { name: 'Orus',     label: 'Orus' },
  { name: 'Puck',     label: 'Puck' },
  { name: 'Zephyr',   label: 'Zephyr' },
  { name: 'Algenib',  label: 'Algenib' },
  { name: 'Achernar', label: 'Achernar' },
  { name: 'Sadachbia',label: 'Sadachbia' },
  { name: 'Umbriel',  label: 'Umbriel' },
]

/**
 * TTS client that calls the backend ``POST /api/tts`` proxy.
 * The backend handles the Gemini API call and caches results on disk.
 * Audio is played via the HTML5 Audio API — no OS voices required.
 */
export class GeminiTTS {
  private currentAudio: HTMLAudioElement | null = null

  /**
   * Synthesise *text* via Gemini TTS and play it immediately.
   *
   * @param text      Plain text to speak.
   * @param voice     Gemini voice name (default ``"Kore"``).
   * @param lang      BCP-47 language code used as a pronunciation hint.
   * @param baseUrl   Backend base URL (default: same origin).
   */
  async speak(
    text: string,
    voice: string,
    lang: string,
    baseUrl = '',
  ): Promise<void> {
    this.stop()
    const response = await fetch(`${baseUrl}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice, lang }),
    })
    if (!response.ok) {
      throw new Error(`TTS request failed: ${response.status} ${response.statusText}`)
    }
    const blob = await response.blob()
    // Server returns audio/wav (PCM wrapped in WAV container)
    const url = URL.createObjectURL(new Blob([await blob.arrayBuffer()], { type: 'audio/wav' }))
    this.currentAudio = new Audio(url)
    this.currentAudio.onended = () => URL.revokeObjectURL(url)
    await this.currentAudio.play()
  }

  /** Stop any currently playing audio immediately. */
  stop(): void {
    if (this.currentAudio) {
      this.currentAudio.pause()
      this.currentAudio = null
    }
  }
}
