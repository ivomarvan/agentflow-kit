# Zadání: Konverzační agent pro rezervaci stolů (Tool Calling, voice-aware)

## Kontext

Restaurace „U Zlatého LLM“ chce nasadit AI asistenta, který přijímá rezervace **přes telefonní hovor i přes web chat**. Agent musí komunikovat se zákazníkem, zjistit potřebné údaje, ověřit kapacitu a vytvořit rezervaci přes interní API. Odpovědi musí být **krátké a vhodné pro TTS** a agent musí zvládat **nejednoznačnosti a chyby z ASR**.

## Cíl

Vytvořit konverzačního agenta využívajícího **Function Calling / Tool Calling** k interakci s mockovaným backendem restaurace. Volba architektury, knihoven, rozhraní a způsobu spuštění je na realizátorovi.

## Mock backend — požadované nástroje

Agent musí mít k dispozici nástroje s tímto chováním (mock, deterministický a testovatelný):

| Nástroj | Vstupy | Chování mocku |
|---------|--------|---------------|
| Kontrola dostupnosti | datum, čas, počet hostů | Pokud je hostů více než 10 **nebo** čas je 20:00 / 20:30 → termín není volný a vrátí alternativní časy (např. 19:00, 21:00). Jinak termín je volný. |
| Vytvoření rezervace | jméno, telefon, datum, čas, počet hostů | Vrátí úspěšné potvrzení včetně ID rezervace. |
| Zrušení rezervace | ID rezervace | Vrátí potvrzení zrušení. |

## Chování agenta (povinné požadavky)

### 1. Sběr informací s repair strategií

Agent musí zjistit: **jméno, telefon, datum, čas, počet osob**.

Při hlasovém vstupu jsou data často nejednoznačná nebo poškozená ASR. Agent musí umět doplnit nebo upřesnit údaje, například:

- *„Chtěl bych stůl na úterý“* → upřesnit konkrétní datum.
- *„stul prodá v sobotu“* (chyba ASR) → pochopit záměr (např. stůl pro dva v sobotu).
- *„v osm“* → upřesnit ráno vs. večer.

### 2. Potvrzení před vytvořením rezervace

Před vytvořením rezervace agent **vždy** zopakuje všechny nasbírané údaje a počká na explicitní souhlas zákazníka (příklad formulace):

> *„Takže rezervuji stůl pro dva, sobota 28. května, 19:00, na jméno Novák, telefon 777 123 456. Mohu rezervaci potvrdit?“*

Nástroj pro vytvoření rezervace smí agent zavolat až po jasném souhlasu. Při odmítnutí nebo požadavku na změnu se vrátí k úpravě údajů.

### 3. Odpovědi vhodné pro hlas

- Krátké věty (maximálně 2 věty na tah konverzace).
- Bez odrážek, URL a dlouhých výčtů.
- Alternativní termíny formulovat přirozeně (např. *„V osm večer máme bohužel plno. Můžu vám nabídnout sedm nebo devět?“*), ne jako strojový seznam časů.

### 4. Chování při chybách a off-topic

- Mimo téma rezervace agent slušně přesměruje zpět k úkolu (např. *„Rád vám pomohu s rezervací. Pro kolik osob byste chtěl stůl?“*).
- Pokud po třech pokusech není jasné, kolik je hostů, agent navrhne přepojení na operátora.

## Minimální technické požadavky

- Agent volá nástroje přes mechanismus tool/function calling vybraného LLM.
- V rámci jedné konverzační relace udržuje historii (paměť) tak, aby navazoval na předchozí tahy.

## Mimo rozsah tohoto dokumentu

Implementační návrhy (architektura stavového automatu, webové UI, konkrétní frameworky, ukázkový kód nástrojů, bonusové scénáře) jsou v souboru [`suggestion.md`](suggestion.md).
