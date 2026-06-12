# Zadání: Hotelový rezervační asistent (voice assistant)

> **Stav:** Zadání aktualizováno po revizi (2026-06-12) — implementace začne po schválení.
> Starý prototyp je zachován v `examples/hotel_booking_bak/`.
>
> **Jazyková politika:** Veškerý kód, systémové prompty, komentáře a nová dokumentace
> jsou **anglicky**. LLM sám odpovídá česky pokud ho uživatel osloví česky.
> Anglický překlad tohoto zadání je v `assignment.en.md`.

---

## 1. Cíl příkladu

Vytvořit **komplexní výukový příklad hlasového asistenta pro rezervaci hotelových pokojů**
implementovaný pomocí frameworku `agentflow`.

Příklad demonstruje:
- Multi-turn konverzaci řízenou stavovým automatem
- Reálný **rezervační workflow** s pravidly, validací a potvrzovacím protokolem
- Ochranu před off-topic vstupy (intent `OTHER` → připomínka účelu bota)
- **Hub-and-spoke** vzor pro sběr dat (více dedikovaných vrcholů místo jednoho iterativního)
- **Live State panel** ve tvaru hotelové knihy (vlastní Vue komponenta)
- Správné uplatnění principů promptování z kurzu (viz kapitola 9)

---

## 2. Datový model hotelu

### 2.1 Pokoje

| ID      | Název            | Lůžka | Cena / noc |
|---------|------------------|------:|----------:|
| `red`   | Červený pokoj    |     3 |   €120    |
| `blue`  | Modrý pokoj      |     2 |    €85    |
| `green` | Zelený pokoj     |     2 |    €85    |
| `white` | Bílý pokoj       |     1 |    €55    |

### 2.2 Rezervace

Každá rezervace: `reservation_id`, `room_id`, `guest_name`, `check_in` (`YYYY-MM-DD`),
`check_out`, `total_price` (computed).

### 2.3 Počáteční stav

| Pokoj   | Host              | Check-in   | Check-out  |
|---------|-------------------|------------|------------|
| Červený | Novák rodina      | 2026-07-10 | 2026-07-14 |
| Modrý   | Jana Dvořáková    | 2026-07-08 | 2026-07-11 |
| Modrý   | Peter Schmidt     | 2026-07-15 | 2026-07-18 |
| Zelený  | Marie Horáková    | 2026-07-12 | 2026-07-15 |
| Bílý    | Tomáš Veselý      | 2026-07-09 | 2026-07-10 |

---

## 3. Live State — Hotelová kniha (GUI panel)

Vlastní Vue komponenta (`HotelBookPanel.vue`) zobrazuje tabulku pokojů × dny.

```
         │ 8.7 │ 9.7 │10.7 │11.7 │12.7 │13.7 │14.7 │15.7 │16.7 │17.7 │
─────────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┼─────┤
Červený  │     │     │Nová │Nová │Nová │Nová │     │     │     │     │
Modrý    │Dvoř │Dvoř │Dvoř │     │     │     │Schm │Schm │Schm │     │
Zelený   │     │     │     │     │Horá │Horá │Horá │     │     │     │
Bílý     │Vese │     │     │     │     │     │     │     │     │     │
```

**Pravidla zobrazení:**
- Sloupce: dynamicky jen dny s alespoň jednou rezervací; rozsah ±1 den od `min(check_in)/max(check_out)`
- Řádky: vždy všechny 4 pokoje (fixní pořadí)
- Buňka: jméno hosta zkráceno na ~4 znaky; prázdná = volný pokoj
- Záhlaví řádku: název pokoje + ikona + cena (např. „🛏 Red Room · 3 beds · €120/night")
- Zvýraznění: nové/zrušené buňky bliknou amber flash (stejný mechanismus jako v SmartHome)
- Komponenta: vlastní `HotelBookPanel.vue` — ne rozšíření `StateViewerPanel.vue`

### 3.1 Pydantic Live State model

```python
class Reservation(BaseModel):
    reservation_id: str
    guest_name: str
    check_in: date
    check_out: date
    total_price: float

class RoomState(BaseModel):
    room_id: str
    name: str
    capacity: int
    price_per_night: float
    reservations: list[Reservation]

class HotelBookState(BaseModel):
    model_config = ConfigDict(frozen=False)
    rooms: list[RoomState]
    last_action: str = ""
```

---

## 4. Architektura agenta (stavový automat)

### 4.1 Přehled vrcholů

```
                    ┌─────────────────────┐
                    │  IntentParserVertex  │
                    │  NEW_BOOKING         │
                    │  CANCELLATION        │
                    │  INQUIRY             │
                    │  OTHER               │  ← nová větev
                    └──────┬──────────────┘
           ┌───────────────┼──────────────┬──────────────┐
           ▼               ▼              ▼               ▼
    DataDispatcher    Cancellation    InquiryVertex   OtherHandler
    Vertex (*)        FlowVertex      (→ StdEnd)      Vertex
           │
     ┌─────┴────────────────────┐
     │  Hub-and-spoke: co chybí?│
     ▼                          │
AskGuestNameVertex ─────────────┤  (vrací se do DataDispatcher)
AskDatesVertex ─────────────────┤
AskCapacityVertex ──────────────┘
           │ data_complete
           ▼
  AvailabilityCheckerVertex  ← volá nástroje
           │
     ┌─────┴──────┐
  volné       obsazené
     │              │
     ▼              ▼
ConfirmationVertex  AlternativesVertex
     │                      │
     │ confirmed             │ alternatives_ok
     ▼                      ▼
BookingExecutorVertex ←─────┘
     │
     ▼
VoiceFormatterVertex → StdEnd
```

(*) `DataDispatcherVertex` zkontroluje co chybí a routuje na správný „ask" vertex.

### 4.2 Nová větev: `OtherHandlerVertex`

Pokud `IntentParserVertex` rozpozná záměr `OTHER` (uživatel se odklonil od tématu),
`OtherHandlerVertex` zdvořile připomene, čeho se voicebot týká, a vrátí se na `IntentParserVertex`.

```
OtherHandlerVertex:
  - Vygeneruje krátkou připomínku: čeho se Emma týká a co může zařídit
  - Znovu se zeptá, jak může pomoci
  - Signál: reminder_sent → IntentParserVertex
  - Maximálně 2 opakování, pak VoiceFormatterVertex + StdEnd
```

### 4.3 Nástroje (Tools)

| Nástroj                    | Popis                                                    |
|----------------------------|----------------------------------------------------------|
| `check_availability`       | Vrátí volné pokoje pro zadaný termín a kapacitu          |
| `get_room_details`         | Detaily pokoje (cena, kapacita)                          |
| `calculate_price`          | Celková cena za pobyt                                    |
| `create_reservation`       | Vytvoří rezervaci (pouze po potvrzení!)                  |
| `cancel_reservation`       | Zruší rezervaci                                          |
| `find_reservation`         | Najde rezervaci podle jméno/datum/ID                     |
| `find_alternatives`        | Alternativní pokoje nebo termíny při konfliktu           |

### 4.4 Signály

```python
class HotelSignal(Signal):
    intent_new       = "intent_new"       # → DataDispatcherVertex
    intent_cancel    = "intent_cancel"    # → CancellationFlowVertex
    intent_inquiry   = "intent_inquiry"   # → InquiryVertex
    intent_other     = "intent_other"     # → OtherHandlerVertex  ← NOVÉ
    reminder_sent    = "reminder_sent"    # → IntentParserVertex (po OTHER)
    data_complete    = "data_complete"    # → AvailabilityCheckerVertex
    need_name        = "need_name"        # → AskGuestNameVertex
    need_dates       = "need_dates"       # → AskDatesVertex
    need_capacity    = "need_capacity"    # → AskCapacityVertex
    name_collected   = "name_collected"   # → DataDispatcherVertex
    dates_collected  = "dates_collected"  # → DataDispatcherVertex
    capacity_collected = "capacity_collected" # → DataDispatcherVertex
    available        = "available"        # → ConfirmationVertex
    unavailable      = "unavailable"      # → AlternativesVertex
    confirmed        = "confirmed"        # → BookingExecutorVertex
    declined         = "declined"         # → StdEnd
    alternatives_ok  = "alternatives_ok"  # → ConfirmationVertex
    done             = "done"             # → VoiceFormatterVertex → StdEnd
```

---

## 5. Rezervační pravidla

- Termíny se překrývají: `new_check_in < existing_check_out AND new_check_out > existing_check_in`
- `check_out` = den odjezdu; nový host může nastoupit v tentýž den
- `check_in >= dnešní datum`; délka 1–30 nocí
- Při konfliktu: nabídnout (1) stejný typ pokoje ±3 dny, (2) jiný pokoj stejné kapacity
- Zrušení: identifikace jméno+datum nebo ID; potvrzení povinné

---

## 6. Komunikační protokol

### 6.1 Confirmation Pattern (kritické)

Před `create_reservation` / `cancel_reservation`:
1. Zopakovat všechny klíčové údaje slovně
2. Čekat na explicitní „ano" / „souhlasím"
3. Teprve pak volat nástroj
4. Nástroj má interní guard: odmítne zápis bez `confirmation_pending=True` v kontextu

### 6.2 TTS výstup

- Max. 2 věty na repliku
- Žádný markdown, odrážky, URL
- Čísla slovy: „tři sta čtyřicet eur", „desátého července"
- Přirozená čeština, důsledné vykání

### 6.3 ASR tolerance

- Tolerovat fonetické chyby, hovorový jazyk, různé formáty dat
- Pokud nerozumí: max. 3 pokusy, pak eskalace
- Parsovat: „desátýho července", „10.7.", „10. 7. 2026" → date

### 6.4 OTHER intent

- Emma má jasné hranice; off-topic dotazy neřeší
- OtherHandlerVertex připomene rozsah a vrátí konverzaci zpět
- Max. 2 připomínky, pak zdvořilé ukončení

---

## 7. Principy promptování z kurzu (shrnutí relevantních pravidel)

### 7.1 Základní techniky (kap. 02)
- **Role/Persona:** Emma má jméno, roli a hranice v každém system promptu
- **Delimitery:** XML tagy (`<tts_constraints>`, `<hotel_info>`) oddělují instrukce od dat
- **Pozitivní instrukce:** „Volej nástroj POUZE po explicitním souhlasu" místo „nevolej bez souhlasu"
- **Formát výstupu:** každý vertex definuje svůj požadovaný výstupní formát

### 7.2 Konverzační AI a voiceboty (kap. 09)
- **TTS constraints:** 2 věty, čísla slovy, žádný markdown — v každém system promptu
- **ASR tolerance:** repair pattern, pravidlo 3 pokusů — v system promptu DataDispatcher
- **Confirmation pattern:** samostatný `ConfirmationVertex` + guard v nástroji
- **Error fallback:** 3× neporozumění → eskalace; off-topic → OtherHandlerVertex

### 7.3 Dekompozice a chaining (kap. 05)
- Sekvenční pipeline: Intent → DataDispatch → Availability → Confirm → Execute → Format
- Hub-and-spoke pro sběr dat: DataDispatcher routuje na specializované „ask" vrcholy
- Každý vrchol = jedna odpovědnost → snazší ladění

### 7.4 Strukturované výstupy (kap. 04)
- Vstupní parametry nástrojů jsou Pydantic modely (garantovaná JSON struktura)
- `IntentParserVertex` vrací enum hodnotu, ne volný text
- `AvailabilityCheckerVertex` vrací strukturovaný seznam, ne popis

### 7.5 Few-shot příklady (kap. 03)
- System prompt `DataDispatcherVertex`: 2–3 příklady různých formátů dat
- System prompt `IntentParserVertex`: příklady edge cases (smíšené záměry, off-topic)

### 7.6 Co záměrně nepoužíváme
- **Chain-of-Thought instrukce:** reasoning modely to dělají interně; pro voicebot příliš pomalé
- **Self-consistency:** zbytečný overhead pro deterministickou rezervační úlohu

---

## 8. Vzorové konverzace pro testování

```
[Happy path]
Uživatel: Chci pokoj pro dva od 15. do 18. července na Horáka.
→ Modrý nebo Zelený, 255 eur, potvrzení, zápis.

[Konflikt]
Uživatel: Rezervujte Modrý pokoj od 8. do 10. července pro Nováka.
→ Konflikt. Alternativa: Zelený (stejná cena) nebo Modrý od 11.7.

[Zrušení]
Uživatel: Zrušte rezervaci Nováka od desátého července.
→ Najde Červený/Novák, zobrazí souhrn, čeká na potvrzení.

[Off-topic]
Uživatel: Jaké je dnes počasí?
→ Emma připomene, čeho se týká. Max 2× pak ukončení.

[ASR chyba]
Uživatel: chci pokoj od desátýho do čtrnástýho črvence
→ Parser správně dekóduje data, pokračuje dál.
```
