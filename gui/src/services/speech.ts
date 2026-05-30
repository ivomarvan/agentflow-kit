/**
 * Thin wrappers around Web Speech API (STT + TTS).
 * Only available in Chrome/Edge — caller should check isSpeechApiSupported() first.
 */

export function isSpeechApiSupported(): boolean {
  return (
    'SpeechRecognition' in window ||
    'webkitSpeechRecognition' in window
  )
}

export interface SpeechRecognitionResult {
  transcript: string
  confidence: number
}

export class SpeechToText {
  // Typed as any because SpeechRecognition is a webkit-prefixed API not always in the TS DOM lib
  private recognition: any

  constructor(lang: string = 'cs-CZ') {
    const SR =
      (window as any).SpeechRecognition ??
      (window as any).webkitSpeechRecognition
    this.recognition = new SR()
    this.recognition.lang = lang
    this.recognition.continuous = false
    this.recognition.interimResults = false
  }

  setLang(lang: string): void {
    this.recognition.lang = lang
  }

  start(
    onResult: (result: SpeechRecognitionResult) => void,
    onEnd: () => void,
    onError: (err: string) => void,
  ): void {
    this.recognition.onresult = (e: any) => {
      const r = e.results[0][0]
      onResult({ transcript: r.transcript, confidence: r.confidence })
    }
    this.recognition.onend = onEnd
    this.recognition.onerror = (e: any) => onError(e.error)
    this.recognition.start()
  }

  stop(): void {
    try { this.recognition.stop() } catch { /* already stopped */ }
  }
}

export class TextToSpeech {
  speak(text: string, voice: SpeechSynthesisVoice | null, lang: string): void {
    window.speechSynthesis.cancel()
    const utt = new SpeechSynthesisUtterance(text)
    utt.lang = lang
    if (voice) utt.voice = voice
    window.speechSynthesis.speak(utt)
  }

  stop(): void {
    window.speechSynthesis.cancel()
  }

  getVoices(): SpeechSynthesisVoice[] {
    return window.speechSynthesis.getVoices()
  }
}

export const STT_LANGUAGES = [
  { code: 'cs-CZ', label: 'Čeština' },
  { code: 'en-US', label: 'English (US)' },
  { code: 'en-GB', label: 'English (UK)' },
  { code: 'de-DE', label: 'Deutsch' },
  { code: 'sk-SK', label: 'Slovenčina' },
] as const
