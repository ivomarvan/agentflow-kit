# Zadání: Interní HR RAG Asistent (chat + voice)

## Kontext
Firma má rozsáhlý dokument "Zaměstnanecká příručka" (pravidla pro dovolenou, home office, benefity, bezpečnost práce). Zaměstnanci se neustále ptají HR oddělení na ty samé otázky. Cílem je RAG (Retrieval-Augmented Generation) asistent, který odpovídá výhradně na základě tohoto dokumentu, **a to jak v textovém, tak v hlasovém režimu** (mikrofon → odpověď nahlas).

## Cíl
Python aplikace, která načte textový dokument, rozseká ho na chunky, spočítá embeddingy a odpovídá na dotazy uživatelů s odkazy na zdroj.

## Hlavní omezení (Kritické!)

### 1. Žádné halucinace
Pokud je dotaz mimo dokument (např. "Jaký je plat ředitele?", "Jaké bude počasí?"), bot **musí** odpovědět: *"Omlouvám se, tuto informaci v zaměstnanecké příručce nevidím."*

### 2. Voice constraints
Asistent má dva režimy a generuje odpovědi v různém stylu:
- **Chat mód:** strukturovaná odpověď, odrážky, citace, max 5 vět.
- **Voice mód (TTS):** **max 2 věty**, žádné odrážky, žádné URL, žádná čísla v závorkách, krátká souvětí. Odpověď musí být příjemná na poslech.

LLM dostane v system promptu indikaci aktivního módu a podle něj přizpůsobí formát.

## Kroky k řešení

1. **Příprava dat:** Vytvořte `hr_manual.md` s vymyšlenými pravidly (25 dní dovolené, 3 dny sick days, home office max 2 dny v týdnu, příspěvek na sport 1000 Kč, atd.). Stačí 1-2 stránky textu, ale s nějakou strukturou (kapitoly).

2. **Ingestion:**
   * Načtěte soubor a rozdělte na smysluplné odstavce (chunks).
   * Embedding přes OpenAI (`text-embedding-3-small`) nebo lokální `sentence-transformers`.
   * Uložení do in-memory dict s kosinovou podobností, NEBO `FAISS` / `ChromaDB`.

3. **Retrieval:**
   * Embedding dotazu → top-K (K=3) nejpodobnějších chunků.
   * Logujte vybrané chunky do konzole pro debug.
   * **Bonus:** přidejte threshold na podobnost - pokud jsou všechny chunky pod threshold, bot rovnou řekne "nevím".

4. **Generation:**
   * Prompt: "Odpovídej VÝHRADNĚ na základě následujícího kontextu. Pokud odpověď v kontextu není, řekni: 'Tuto informaci v příručce nevidím.'"
   * V system promptu přepínejte mezi chat/voice módem.

## Webové UX (DOPORUČENO)

### Backend
- `FastAPI` se dvěma endpointy:
  - `POST /chat` - vstup `{question, mode: "chat"|"voice"}`, výstup `{answer, sources}`.
  - (volitelně) `GET /` - servíruje statický `index.html`.

### Frontend (vanilla HTML+JS, ~ 100 řádků)
Jeden statický `index.html` s:
- Textboxem pro dotaz + tlačítko "Pošli".
- Tlačítkem **🎤 Mluv** používajícím `webkitSpeechRecognition` s `lang = 'cs-CZ'`.
- Toggle mezi režimy chat/voice.
- Ve voice režimu: po obdržení odpovědi automaticky `speechSynthesis.speak(new SpeechSynthesisUtterance(answer))` (s nastaveným českým hlasem, pokud je dostupný: `voices.find(v => v.lang.startsWith('cs'))`).
- Zobrazení transkriptu konverzace + použité zdroje (chunks).

### Proč Web Speech API?
- Funguje out-of-the-box v Chrome (`webkitSpeechRecognition`).
- Žádný extra setup (Whisper, Coqui, IBM Watson).
- Pro učení a prototyp ideální. Pro produkci by se použilo dedikované ASR/TTS, ale tohle stačí pro pochopení voice constraints.

## Technické požadavky
* Nepoužívejte LangChain a podobné frameworky - napište RAG "od nuly" s OpenAI/Anthropic SDK, abyste rozuměl, co se děje.
* Logujte vybrané chunky pro každý dotaz.
* Ošetřete edge case: prázdný dotaz, dotaz mimo doménu, příliš dlouhý dotaz.
