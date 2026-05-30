# Zadání: Konverzační agent pro rezervaci stolů (Tool Calling, voice-aware)

## Kontext
Restaurace "U Zlatého LLM" chce nasadit AI asistenta, který přijímá rezervace **přes telefonní hovor i přes web chat**. Agent musí umět komunikovat se zákazníkem, zjistit potřebné údaje, ověřit kapacitu a vytvořit rezervaci přes interní API. Jde o voicebot, takže odpovědi musí být **krátké, vhodné pro TTS**, a musí umět zvládnout **chyby z ASR**.

## Cíl
Konverzační agent využívající **Function Calling / Tool Calling** k interakci s (mockovaným) backendem. Implementace buď čistým cyklem v Pythonu, nebo `LangGraph` jako stavový automat.

## Nástroje (Tools), které má agent k dispozici

```python
def check_availability(date: str, time: str, guests: int) -> dict:
    """
    Mock: vrátí {"available": False, "alternatives": ["19:00", "21:00"]}
    pokud guests > 10 nebo time in ["20:00", "20:30"]; jinak {"available": True}.
    """

def create_reservation(name: str, phone: str, date: str, time: str, guests: int) -> dict:
    """
    Mock: vrátí {"status": "success", "reservation_id": "RES-12345"}.
    """

def cancel_reservation(reservation_id: str) -> dict:
    """
    Mock: vrátí {"status": "cancelled"}.
    """
```

## Chování agenta (povinné požadavky)

### 1. Sběr informací s repair strategií
Agent musí zjistit: jméno, telefon, datum, čas, počet osob.

Při hlasovém vstupu jsou data často **nejednoznačná nebo zmrzačená ASR**:
- *"Chtěl bych stůl na úterý"* → agent: *"Promiňte, na úterý 27. května nebo 3. června?"*
- *"stul prodá v sobotu"* (ASR error) → agent musí pochopit "stůl pro dva v sobotu"
- *"v osm"* → agent: *"V osm hodin ráno, nebo večer?"*

### 2. Confirmation pattern (KRITICKÉ!)
Před voláním `create_reservation` agent **vždy** zopakuje všechny údaje a počká na potvrzení:

> *"Takže rezervuji stůl pro dva, sobota 28. května, 19:00, na jméno Novák, telefon 777 123 456. Mohu rezervaci potvrdit?"*

Až po jasném "ano" agent zavolá tool. Při "ne" / "počkat" / "změnit čas" se vrací k editaci. Tohle je standard ve voice produkci - chyba je drahá, takže se *vždycky* potvrzuje.

### 3. Voice-friendly odpovědi
- **Krátké věty** (max 2 věty na turn).
- Žádné odrážky, žádné URL, žádné dlouhé výčty.
- Při alternativách mluvit přirozeně: *"V osm večer máme bohužel plno. Můžu vám nabídnout sedm nebo devět?"* (ne *"Dostupné časy: 19:00, 21:00"*).

### 4. Chování při chybách
- Pokud uživatel řekne něco mimo téma (smalltalk, off-topic), agent slušně přesměruje: *"Rád vám pomohu s rezervací. Pro kolik osob byste chtěl stůl?"*
- Pokud po 3 pokusech není jasné, kolik je hostů, agent navrhne přepojení na operátora.

## Technické požadavky
* Definice toolů přesně podle JSON schématu vybraného LLM (OpenAI tools / Anthropic tools).
* Agent udržuje historii konverzace (paměť) - buď v paměti procesu, nebo per-session v dict.
* **Doporučená architektura:** `LangGraph` se stavy `collecting_info → confirming → executing → done`. Pokud LangGraph je moc, čistý `while` cyklus s tool-calling smyčkou je v pohodě.
* Logujte každé volání toolu (jaký nástroj, jaké argumenty, jaký výsledek) - to bude užitečné při post-mortem analýze konverzací.

## Webové UX (DOPORUČENO)

### Backend
- `FastAPI` s endpointem `POST /chat`:
  - vstup: `{session_id, user_message}`,
  - výstup: `{assistant_message, state, tool_calls: [...]}`.
- Stav konverzace per `session_id` v paměti / SQLite.

### Frontend (`index.html` + vanilla JS)
- Chat box s historií konverzace.
- Tlačítko **🎤 Mluv** (Web Speech API, `lang = 'cs-CZ'`):
  - jednorázové rozpoznávání (`continuous = false`),
  - po výsledku rovnou POST na backend,
  - odpověď přečtená přes `speechSynthesis` (česky).
- **Debug panel** vpravo: zobrazení `tool_calls` (jaký nástroj agent volá, s jakými argumenty, jaká odpověď). Tohle je **klíčové** pro pochopení, jak agent přemýšlí.
- Toggle voice/text mode.

### Bonus: Simulace ASR errorů
Pokud nechcete řešit mikrofon, vytvořte sadu testovacích vstupů, které simulují typické chyby ASR (chybějící diakritika, špatně rozdělená slova). Agent by je měl zvládnout.

## Co byste si měl z tohoto projektu odnést
1. **Function calling smyčka** - jak vypadá interakce LLM ↔ Python tools v praxi.
2. **State management** - kdy si pamatovat, kdy zapomenout, kdy resetovat.
3. **Voice constraints** - jak moc se odpověď liší pro chat vs. hlas.
4. **Confirmation pattern** - production-ready zvyk, který odlišuje "demo" od "real product".
