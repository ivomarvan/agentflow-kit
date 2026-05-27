# Zadání: Outbound voicebot pro HR screening (Adéla-style)

## Kontext
Tohle je **capstone projekt** spojující všechny předchozí dovednosti - extrakce, RAG, tool calling, voice constraints - do jednoho realistického produktu. Inspirace: virtuální recruiter **Adéla** od Telmy/Mama AI, která vyhrála AI Awards 2024 v kategorii AI for Government.

Voicebot zavolá kandidátovi, který reagoval na inzerát, a provede s ním krátký předkvalifikační rozhovor. Cílem je odsít zjevně nevhodné kandidáty a předat lidskému recruiterovi strukturovaný profil těch nadějných.

## Cíl
**Voice-first** konverzační agent v Pythonu s webovým UX, který:
1. Zahájí konverzaci pozdravem a krátkým představením.
2. Zjistí cca 5-7 informací od kandidáta.
3. Po cestě potvrzuje diktované údaje (jméno, telefon).
4. Na konci uloží **strukturovaný profil** + **doporučení** (pokračovat / nepokračovat / hraniční).
5. Slušně se rozloučí.

## Scénář (use case)

Pozice: **Operátor zákaznického servisu** v call centru.

Voicebot musí zjistit:
1. **Zájem o pozici** - opravdu má kandidát aktuálně zájem? (Někteří se hlásí "do zásoby".)
2. **Dostupnost** - od kdy by mohl nastoupit? (preferujeme do 1 měsíce)
3. **Mzdové očekávání** - rozumí naší mzdové vidlici 35-45 tis. Kč? (vyfiltrujeme ty, co chtějí 60+)
4. **Klíčové dovednosti** - čeština rodilý mluvčí + alespoň B2 angličtina + zkušenost s call centrem (alespoň 6 měsíců).
5. **Práce na směny** - je ochoten pracovat na ranní/odpolední/noční směny vč. víkendů?
6. **Otázky kandidáta** - prostor pro 1-2 otázky kandidáta.

## Povinné požadavky

### 1. Konverzační design (CORE)
Tohle je **klíčová dovednost**, kterou Mama AI hledá. Vytvořte v dokumentu `doc/conversation_design.md` návrh konverzace:
- **Opening:** přesné znění úvodu (5-10 sec).
- **Pro každý "info slot":** jak se otázka přirozeně zeptá, jak se zachová bot při různých odpovědích (jasná / nejednoznačná / mimo téma).
- **Closing:** jak se rozloučit v různých scénářích (pokračovat / nepokračovat / hraniční).
- **Repair patterns:** co dělá bot, když nerozumí, když uživatel mluví moc rychle, když uživatel chce mluvit s člověkem.

### 2. State management
Použijte `LangGraph` (nebo čistý stavový automat) - voicebot má jasné fáze:
```
greeting → ask_interest → ask_availability → ask_salary
→ ask_skills → ask_shifts → kandidate_questions → closing
```
Každý uzel má vstupní a výstupní podmínky. Při chybě (3 neúspěšné pokusy o zjištění slotu) přejde do `escalate_to_human`.

### 3. Confirmation pattern
Diktované údaje (jméno, telefon, mzdové očekávání) **vždy** zopakovat:
> *"Rozumím správně - jmenujete se Jana Nováková a vaše telefonní číslo je sedm sedm sedm jedna dva tři čtyři pět šest? Je to tak?"*

### 4. Voice constraints
- Krátké věty, max 2 věty na turn.
- Žádné odrážky, žádné URL.
- Empatický, ale profesionální tón.
- Tykání NEBO vykání - rozhodnout v conversation designu a držet konzistentně.

### 5. Czech-specific (KRITICKÉ pro Telmu)
- Správné **skloňování** v generovaných větách: *"Děkuji, paní Nováková"* vs *"Děkuji, pane Novák"*. Nejjednodušší řešení: pokud LLM neumí spolehlivě, ptejte se kandidáta v 5. pádu od začátku ("Jak vám mám říkat?").
- Při čtení čísel přes TTS: *"sedm set sedmdesát sedm"* je přijatelné, ale *"7-7-7"* nebo *"7 7 7"* TTS čte špatně. Při generaci odpovědi LLM by měl psát čísla **slovy**, pokud je má bot vyslovit nahlas.

### 6. Strukturovaný výstup
Na konci hovoru bot uloží `KandidateProfile` (Pydantic):
```python
class KandidateProfile(BaseModel):
    name: str
    phone: str
    interested: bool
    available_from: str  # např. "ihned", "do měsíce", "za 2 měsíce", "později"
    salary_expectation_kc: int | None
    czech_native: bool
    english_level: str  # "A2", "B1", "B2", "C1+", "neuvedeno"
    callcenter_experience_months: int | None
    shifts_ok: bool
    candidate_questions: list[str]
    
    # Doporučení
    recommendation: Literal["pokracovat", "nepokracovat", "hranicni"]
    recommendation_reasoning: str
    full_transcript: list[dict]
```

## Webové UX (POVINNÉ pro tento projekt)

### Backend
- `FastAPI`:
  - `POST /session/start` - založí novou session, vrátí session_id + úvodní pozdrav.
  - `POST /session/{id}/turn` - přijme user_message (z STT), vrátí bot_message (pro TTS).
  - `GET /session/{id}/profile` - po skončení vrátí `KandidateProfile`.
- Persistence: SQLite nebo prostě JSON soubor per session.

### Frontend (`index.html` + JS)
- **Voice-first UX** s těmito prvky:
  - Velké tlačítko **🎤 Mluv** - drží se stisknuté po dobu mluvení (push-to-talk), nebo continuous mode.
  - Vizualizace stavu: "Bot mluví" / "Poslouchám" / "Přemýšlím".
  - Transkript konverzace pod tlačítkem (live).
  - Po skončení hovoru se zobrazí výsledný `KandidateProfile` v hezké kartě.
- **Web Speech API:**
  - `webkitSpeechRecognition` s `lang = 'cs-CZ'`, `continuous = false`, `interimResults = true` pro live feedback.
  - `speechSynthesis.speak(...)` s českým hlasem (vybrat z `speechSynthesis.getVoices()`, filtr `v.lang.startsWith('cs')`).
  - Důležité: volat `speechSynthesis.cancel()` když user začne mluvit (barge-in pattern).
- **Toggle text mode** - pro testování bez mikrofonu.

## Technické požadavky
* Reset session - aby se dalo testovat opakovaně bez restartu serveru.
* Logování každého turn-u (timestamp, user input, bot output, vybraný stav, volané tooly) - to bude užitečné při post-mortem analýze (přesně Mama AI workflow).
* `pytest` test alespoň jedné kompletní konverzace - mock LLM odpovědí, ověřit, že stavový automat projde celým flow správně.

## Tools (volitelně, pro pokročilejší verzi)

```python
def save_candidate_profile(profile: dict) -> dict:
    """Uloží profil do DB (mock)."""

def schedule_followup_interview(candidate_id: str, preferred_time: str) -> dict:
    """Naplánuje navazující osobní pohovor (mock)."""
    
def transfer_to_human_recruiter() -> dict:
    """Eskalace na lidského recruitera."""
```

Pokud bot na konci doporučí "pokracovat", může nabídnout naplánování dalšího kola a zavolat `schedule_followup_interview`.

## Co byste si měl z tohoto projektu odnést

1. **Conversation design jako disciplína** - to je 50 % práce na voicebotu, ne kód.
2. **State machine + LLM** - kdy nechat LLM rozhodovat volně, kdy ho omezit hard-coded přechody.
3. **Voice-first UX** - vlastní zkušenost, jak rozdílné to je oproti chatu.
4. **End-to-end voicebot** od mikrofonu po strukturovaný výstup pro lidského operátora.
5. **Czech-specific challenges** - skloňování, čtení čísel, formality.

## Reálnost / poznámka
Ano, tohle je hodně věcí na 4 hodiny domácího úkolu. Ale **přesně tohle dělá Telma**, a pokud projdete tímto projektem byť jen na 70 %, budete mít **konkrétní portfolio** ukázku, kterou můžete u technického interview otevřít a říct: *"Tohle jsem si postavil pro pochopení vaší domény. Můžeme se na to spolu podívat?"* - to je extrémně silný signál.
