# Zadání: Extrakce strukturovaných dat ze zákaznické komunikace

## Kontext
Firma provozující e-shop dostává denně stovky e-mailů, chatových zpráv a **přepisů hovorů ze zákaznické linky** (voicebot/call centrum). Zákaznická podpora nestíhá zprávy třídit. Vaším úkolem je vytvořit AI skript, který z nestrukturovaného textu (často plného emocí, překlepů, **chyb z ASR/STT** a zmatených informací) vytáhne přesná strukturovaná data pro další zpracování v interním systému.

## Cíl
Napsat Python skript, který přijme textovou zprávu zákazníka a pomocí LLM (OpenAI nebo Anthropic) vrátí striktně validovaný JSON objekt (ideálně pomocí knihovny `pydantic`).

## Požadavky na výstup (Pydantic model)
LLM musí z textu extrahovat následující pole:
1. `customer_name` (string) - Jméno zákazníka (pokud je uvedeno, jinak `None`).
2. `order_id` (string) - Číslo objednávky. Zákazníci ho píšou v různých formátech ("obj. č. 123-456", "#123456") a v hlasovém přepisu ho **diktují slovy** ("devět devadesát osm dvě stě třicet čtyři jedenáct"). Normalizujte na čistý string číslic.
3. `issue_category` (enum) - Kategorie problému. Striktně jedna z hodnot: `LATE_DELIVERY`, `DAMAGED_GOODS`, `WRONG_ITEM`, `REFUND_REQUEST`, `OTHER`.
4. `sentiment_score` (int) - Naštvanost zákazníka 1 (velmi naštvaný) až 5 (klidný/spokojený).
5. `is_escalation_needed` (bool) - True, pokud zákazník vyhrožuje ČOI, právníkem nebo medializací.

## Testovací data (3 typy vstupů - povinně všechny)

### A) E-mail (čistý text)
*"Dobrý den, včera mi přišel ten mixér (číslo obj. 998 234 11), ale má prasklou nádobu! Jsem hrozně zklamaná, potřebuju ho na víkend. Chci okamžitou výměnu nebo peníze zpět, jinak to dám na Facebook! S pozdravem, Jana Nováková"*

### B) Chatová zpráva (krátká, neformální)
*"Kde je moje objednávka #8833?? Měla tu být už v úterý. Karel"*

### C) Přepis hovoru z ASR (Telma-relevantní!)
Realistický přepis řeči obsahuje:
- **diktovaná čísla slovy:** *"devět devět osm dvě stě třicet čtyři jedenáct"*
- **vycpávková slova:** *"ehm", "no", "jako", "prostě"*
- **chyby rozpoznávače:** misheard slova, chybějící diakritika, špatně rozdělené věty
- **bez interpunkce a velkých písmen**

Příklad:
*"jo dobrý den ehm já bych chtěla reklamovat ten mixér mám tady číslo objednávky devět devět osm dvě stě třicet čtyři jedenáct prasklá tam ta nádoba prostě a já to potřebuju na víkend tak buď výměnu nebo peníze zpátky"*

## Technické požadavky
* Použijte moderní přístup ke strukturovaným výstupům:
  * `client.responses.parse(...)` / `client.beta.chat.completions.parse(...)` (OpenAI),
  * tool calling s Pydantic schématem (Anthropic Claude).
* Robustní ošetření chyb (LLM vrátí špatný formát → retry nebo fallback).
* Napište alespoň 3 `pytest` testy - po jednom pro každý typ vstupu (A/B/C). Klíčový je test C - správná normalizace čísla diktovaného slovy.
* **Bonus:** porovnejte úspěšnost stejného promptu na vstupech A vs. C (kolik % polí extrahováno správně). Tohle je přesně ten typ analýzy, kterou Mama AI dělá nad reálným provozem.

## Webové UX
**Není potřeba.** Tento projekt je čistě batch processing - vstupem je text, výstupem JSON. Soustřeďte se na kvalitu extrakce, ne na UI.
