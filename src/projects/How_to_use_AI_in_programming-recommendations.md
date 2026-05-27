# Jak používat AI při kódování těchto cvičných projektů

## Účel dokumentu
Doporučení, do jaké míry využívat AI agenty (Cursor Composer, Codex, jiné) při řešení projektů v `self_education/AI_example_projects/`. Cíl těchto projektů je **učení**, ne dodání produktu - proto je optimální poměr "AI vs. ruční práce" jiný než v běžných pracovních projektech.

## Klíčové napětí

V produkčních projektech APM workflow (viz `cursor-best-practices-template/rules/07-project-management.mdc`) optimalizuje rychlost a kvalitu dodávky. Necháte Plannera dekomposovat, Coder implementuje, vy reviewujete. Cílem je **kód**.

U těchto cvičných projektů je cíl jiný:
- naučit se RAG, tool calling, conversation design, voice constraints,
- být schopen řešení obhájit při technickém pohovoru.

Pokud necháte AI agenta napsat agent loop za vás, máte fungující kód za 20 minut a **nenaučili jste se nic**. Při follow-up otázce *"proč jste použil tool calling se streaming a jaké by byly alternativy?"* nebudete schopen odpovědět.

## APM artefakty - co používat a co vynechat

| APM artefakt | Co s tím u učebních projektů | Proč |
|---|---|---|
| `brief.md` | Hotovo (vygeneroval AI s lidskou revizí). | OK. |
| `spec.md` | **Pište SAMI ručně.** Bez agenta. | Akt psaní specifikace = nucené přemýšlení o architektuře. To je 50 % učení. |
| `roadmap.md` | **Vynechte.** | Pro 1-projekt scope zbytečné. |
| `epic-NNN/plan.md` | **Vynechte.** | Příliš těžkotonážní. |
| `task-NNN/spec.md` | **Vynechte** nebo použijte jako rychlý outline (5 řádků v hlavě). | Stejný argument. |
| Implementace | **Hybrid** - viz tři zóny níže. | Nejdůležitější rozhodnutí. |
| `task-NNN/dod.md` | **Volitelně.** Self-checklist před prohlášením "hotovo". | Brzda perfekcionismu. |
| `task-NNN/report.md` | **Doporučuji** napsat po dokončení každého projektu. | Forced retrospection - pomůže pak v interview odpovídat *"proč jste to udělal takhle"*. |

**Závěr:** zachovejte z template strukturu adresářů (`doc/project-progress/`), ale z workflow použijte jen `brief → spec → implementation → report`. Žádné epic plans, žádné task specs s YAML headery, žádné DoD checklisty.

## Tři zóny pro využití AI při kódování

### RED ZONE - Pište SAMI, bez AI
Pokud to napíše AI, nenaučíte se nic, co by vám pomohlo u Telmy / Mama AI.

- **Návrh promptů** (system prompt, few-shot examples, repair patterns).
- **Návrh Pydantic schémat** pro tooly a strukturované výstupy.
- **Conversation design** v projektu 05 (`conversation_design.md`).
- **Architektura state machine** (které stavy, jaké přechody).
- **Volba chunking strategie** v RAG (po větách / odstavcích / sliding window?).
- **Konkrétní agent loop** - cyklus "LLM → tool call → tool result → LLM".
- **Decision na klíčové trade-offs** (LangGraph vs. čistý cyklus, in-memory vs. vector DB).

### YELLOW ZONE - AI jako "pair programmer", vy řídíte
Můžete kódovat sami a AI volat na rychlé otázky ("jak se v openai SDK volá structured outputs?"), ale **kód píšete vy**, jen ho AI případně čistí/opravuje.

- Implementace agent loop (kód odpovídající vašemu návrhu z RED zóny).
- Pydantic modely (vy definujete fields, AI pomůže s validátory).
- Pytest testy (vy specifikujete co testovat, AI pomůže se setupem).
- Refactoring vašeho kódu.
- Debugging - zde je AI extrémně užitečné.

### GREEN ZONE - Plně delegovat na AI
Zde je AI rychlejší a vy se nic nového nenaučíte (resp. to není to, co se chcete naučit pro Mama AI).

- FastAPI boilerplate (`POST /chat` endpoint, CORS, error handling).
- HTML + vanilla JS frontend s Web Speech API.
- SQLite schéma + ORM helpers.
- Konfigurace (`.env`, `pyproject.toml`, `Dockerfile`).
- Logování, formátování výstupu.

## Doporučený workflow pro každý projekt

```
1. Přečíst brief.md                                (5 min)
2. Napsat spec.md SAMI                             (15-30 min)   ← RED
   - Architektura (komponenty, data flow)
   - Pydantic modely
   - Pseudokód agent loop
   - Struktura promptu
3. Napsat prompty SAMI                             (15-30 min)   ← RED
4. AI generuje boilerplate (FastAPI, JS frontend)                ← GREEN
5. Vy píšete core logiku                                          ← YELLOW (s AI jako pair)
6. AI píše testy podle vaší specifikace                          ← YELLOW
7. Spustit, debug, iterovat                                       ← YELLOW (AI pomůže)
8. Napsat report.md - co jsem se naučil           (10 min)       ← RED
```

## Speciální doporučení: Take-home simulace

**Alespoň jeden z 5 projektů řešit úplně bez AI agentů**, jen s oficiální dokumentací a Stack Overflow. Ne kvůli dogma, ale abyste znal **svou reálnou rychlost**.

Pokud na 4h take-home pohovor dorazíte s vírou, že to "zvládnete bez AI", a pak se ukáže, že potřebujete 8 hodin, je to problém. Lepší to vědět dopředu.

**Doporučený kandidát: Project 03 (Tool calling).** Není ani moc malé, ani moc velké - dobrý benchmark.

## TL;DR

1. **Brief** - hotový.
2. **Spec** - 30 min ruční psaní per projekt (RED zone).
3. **Prompty + agent loop** - ručně (RED zone).
4. **Boilerplate (FastAPI, frontend)** - delegovat na AI (GREEN zone).
5. **Core logic implementace** - pair-programming s AI (YELLOW zone).
6. **Testování + debug** - pair s AI (YELLOW zone).
7. **Report** - 10 min ruční psaní per projekt (RED zone).
8. **Bonus** - jeden projekt totálně bez AI agentů (kalibrace rychlosti).

Cíl: nejen znalosti, ale **reálná důvěra** ve vlastní schopnosti. Při technickém pohovoru musíte vědět, **proč** je váš kód takový, jaký je, a umět to obhájit.

## Pro reálný take-home (Mama AI / Telma)

- AI tools budou pravděpodobně povoleny (jsou to AI firmy).
- Ale kód budete **obhajovat live**, často s follow-up úpravami při interview.
- Doporučení: AI ano, ale **každý větší blok kódu si nejdřív promyslete v hlavě**, pak teprve nechte AI generovat. Validace AI výstupu je rychlejší než návrh řešení od nuly.
- Chovejte se k AI jako k juniornímu kolegovi - dobré nápady občas má, ale rozhodnutí o architektuře a klíčových vzorcích je vaše.
