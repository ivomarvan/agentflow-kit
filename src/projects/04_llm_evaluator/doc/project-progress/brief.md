# Zadání: LLM-as-a-Judge - evaluace voicebot konverzací

## Kontext
Vyvinuli jste nového AI voicebota pro call centrum, který řeší reklamace. Potřebujete automatizovaně měřit kvalitu komunikace, aniž byste museli číst tisíce transkriptů ručně. Využijete silnější LLM (GPT-4o, Claude 3.5+ Sonnet) jako "porotce" (Judge), který hodnotí výstupy vašeho bota podle definovaných kritérií.

Tohle je přesně to, co Mama AI dělá - *"iterative improvements based on deep analysis of user traffic"*.

## Cíl
Evaluační skript, který:
1. Načte transkripty konverzací (uživatel ↔ bot).
2. Předloží je LLM porotci spolu s hodnotícími kritérii.
3. Získá strukturované hodnocení (Pydantic) - skóre + zdůvodnění.
4. Spočítá agregovanou statistiku přes celou dávku.

## Vstupní data (`transcripts.jsonl`)

Každý řádek = jedna konverzace (pole zpráv). Připravte si **alespoň 10** ručně psaných konverzací různé kvality (některé dobré, některé záměrně špatné), abyste si ověřil, že judge skutečně rozlišuje.

Příklad jedné konverzace:
```json
[
  {"role": "user", "content": "Dobrý den, nepřišel mi balíček, co s tím jako budete dělat?!"},
  {"role": "bot", "content": "Uklidněte se. Dejte mi číslo objednávky."},
  {"role": "user", "content": "Jak uklidněte se? Číslo je 12345."},
  {"role": "bot", "content": "Objednávka 12345 se ztratila. Peníze vám vrátíme na účet."}
]
```

## Hodnotící kritéria

Porotce musí každou konverzaci ohodnotit na škále **1 (nejhorší) až 5 (nejlepší)** v následujících metrikách:

### 1. Empatie a profesionalita (Politeness)
Byl bot zdvořilý, empatický a profesionální? Nepoužil neprofesionální fráze ("Uklidněte se")? Tykal/vykal konzistentně?

### 2. Efektivita řešení (Efficiency)
Vyřešil bot problém zákazníka? Zjistil potřebné údaje? Nabídl konkrétní řešení?

### 3. Vhodnost pro hlasový kanál (Voice Suitability) **NEW**
Byly bot odpovědi vhodné pro TTS / poslech?
- **5:** krátké, plynulé, srozumitelné věty.
- **3:** občas dlouhé souvětí nebo technický jargon, ale srozumitelné.
- **1:** dlouhé výčty, URL, číselné kódy, odrážky - nesrozumitelné když se přečtou nahlas.

Tato metrika je **specifická pro Telmu** - jejich produkt je voicebot, takže "vhodnost pro hlas" je kritická.

### 4. Bonus: Czech grammar quality
Volitelná čtvrtá metrika - kvalita češtiny (správné skloňování, žádné kostrbaté překlady, žádné anglicizmy).

## Výstup (Pydantic model)

```python
class EvaluationResult(BaseModel):
    politeness_score: int  # 1-5
    politeness_reasoning: str
    efficiency_score: int  # 1-5
    efficiency_reasoning: str
    voice_suitability_score: int  # 1-5
    voice_suitability_reasoning: str
    overall_summary: str  # 2-3 věty
```

## Agregace přes dávku
Skript musí na konci vypsat:
- **Průměrné skóre** pro každou metriku přes celou dávku.
- **Top 3 nejhorší konverzace** (nejnižší overall) s důvody - to jsou kandidáti na opravu promptu / fine-tuning.
- (Bonus) **Korelace mezi metrikami** - např. zhoršuje se "voice suitability" společně s "politeness"? To může napovědět systémový problém.

## Technické požadavky

### Konzistence judge
LLM porotci jsou notoricky **nekonzistentní**. Implementujte alespoň jednu z těchto strategií:

1. **Few-shot prompting:** v promptu dejte 1-2 ukázkové hodnocení (jeden dobrý, jeden špatný transkript + očekávaný výstup).
2. **Self-consistency:** zavolejte judge 3x se stejným vstupem (`temperature=0.3`) a vezměte medián.
3. **Detailní rubric:** v system promptu definujte přesně, co znamená každá hodnota škály (1, 2, 3, 4, 5) - aby porotce neflaktoval.

Vyzkoušejte si, který přístup dává nejstabilnější výsledky.

### Reproducibility
* Verzujte si verzi modelu (`gpt-4o-2024-11-20`, ne `gpt-4o`).
* Logujte všechny vstupy a výstupy do souboru pro pozdější analýzu.
* `temperature=0` nebo `0.3` (pro experimenty s self-consistency).

## Webové UX
**Není potřeba.** Evaluace je čistě batch process. Stačí dobře formátovaný výstup do konzole / TSV / JSON. Pokud byste chtěl, vygenerujte HTML report s tabulkou skóre + barevně označenými problematickými konverzacemi - to je užitečnější než UI.

## Co byste si měl z tohoto projektu odnést
1. **Jak myslí LLM porotce** - co potřebuje v promptu, aby hodnotil konzistentně.
2. **Pydantic pro strukturované hodnocení** - nejen výstup, ale i validace skóre v rozsahu 1-5.
3. **Agregace a interpretace** - skóre samo o sobě nestačí, důležité je _proč_.
4. **Voice suitability jako samostatná metrika** - klíčový rozdíl mezi chat a voice botem.
