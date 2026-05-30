---
apm_category: epic-plan
apm_ref: E100
apm_level: epic
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-05-30
updated_at: 2026-05-30
approved_by: Human
approved_at: 2026-05-30
---

# Epic E100 — VoiceBot záložka

**Cíl:** Přidat záložku **VoiceBot** — totéž jako Chat, ale vstup a výstup je hlasový.
Využívá Web Speech API (Chrome/Edge). Výběr jazyka a hlasu výstupu. Backend sdílí
`POST /api/run` a WebSocket z E097.

---

## Scope

| Oblast | Co se mění |
|--------|-----------|
| `gui/src/components/voicebot/` (nový) | VoiceBot záložka |
| `gui/src/services/speech.ts` (nový) | STT + TTS wrapper nad Web Speech API |
| `gui/src/App.vue` | Aktivovat záložku VoiceBot |
| `gui/README.md` | Sekce: VoiceBot požadavky (Chrome/Edge) |

---

## Task List

| Task | Název | Závisí na |
|------|-------|-----------|
| T010 | Speech service: STT + TTS wrapper | E098 |
| T020 | VoiceBot záložka komponenta | T010 |
| T030 | Výběr jazyka a hlasu + aktivace záložky | T020 |

---

## T010 — Speech service

### `src/services/speech.ts`

```typescript
export class SpeechToText {
    private recognition: SpeechRecognition

    constructor(lang: string = 'cs-CZ') { ... }

    start(onResult: (text: string) => void, onEnd: () => void): void { ... }
    stop(): void { ... }
}

export class TextToSpeech {
    speak(text: string, voice: SpeechSynthesisVoice | null, lang: string): void { ... }
    stop(): void { ... }
    getVoices(): SpeechSynthesisVoice[] { ... }
}

export function isSpeechApiSupported(): boolean {
    return 'SpeechRecognition' in window || 'webkitSpeechRecognition' in window
}
```

Web Speech API je dostupné pouze v Chrome/Edge. Firefox a Safari nepodporují STT.
GUI zobrazí upozornění pokud `!isSpeechApiSupported()`.

---

## T020 — VoiceBot záložka

### Komponenty

```
src/components/voicebot/
    VoiceBotView.vue        ← hlavní záložka
    VoiceButton.vue         ← mic tlačítko s animací
    VoiceTranscript.vue     ← live přepis + výsledek
```

### UX flow

1. Uživatel klikne na mic ikonu (nebo stiskne Space)
2. Indikátor nahrávání (animace)
3. STT → text → odeslání na `POST /api/run`
4. WS events → průběh viditelný jako text
5. Po `run_complete`: TTS přečte výsledek hlasem

### Sdílení conversation s Chat záložkou

`useChatStore` je sdílený — VoiceBot přidává zprávy do stejné history jako Chat.
Uživatel může přepínat mezi záložkami a vidí celou historii.

---

## T030 — Výběr jazyka a hlasu

### Nastavení hlasu

```
src/components/voicebot/
    VoiceSettings.vue       ← dropdown: hlas výstupu + jazyk STT
```

```typescript
// Dostupné jazyky pro STT (Web Speech API)
const STT_LANGUAGES = [
    { code: 'cs-CZ', label: 'Čeština' },
    { code: 'en-US', label: 'English (US)' },
    { code: 'en-GB', label: 'English (UK)' },
    { code: 'de-DE', label: 'Deutsch' },
    { code: 'sk-SK', label: 'Slovenčina' },
]
```

TTS hlasy: načteny z `speechSynthesis.getVoices()` — liší se podle OS a browseru.

### Aktivace záložky v `App.vue`

```html
<TabPanel value="voicebot" :disabled="!speechSupported">
    <VoiceBotView />
    <template #header>
        🎤 VoiceBot
        <Badge v-if="!speechSupported" value="Chrome only" severity="warn" />
    </template>
</TabPanel>
```

---

## Epic E100 Definition of Done

- [ ] Záložka VoiceBot aktivní v App.vue
- [ ] Klik na mic → STT → zobrazí přepis → odeslání na `/api/run`
- [ ] Po `run_complete` → TTS přečte výsledek
- [ ] Výběr jazyka STT funkční (CS, EN-US, EN-GB, DE)
- [ ] Výběr hlasu TTS ze systémových hlasů
- [ ] Upozornění pokud prohlížeč nepodporuje Web Speech API
- [ ] Conversation history sdílená s Chat záložkou
- [ ] Pre-built dist aktualizován
