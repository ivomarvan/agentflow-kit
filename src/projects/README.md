# AI Example Projects

## Účel
Sada cvičných projektů pokrývající typické úkoly v oblasti AI agentů a konverzačních systémů. Každý projekt procvičí jednu konkrétní dovednost a dohromady tvoří ucelenou učební sestavu.

**Domény:** speech recognition, NLP/NLU, dialog systems, voice + chat, čeština.

## Přehled projektů

### 01 - Structured Extraction
**Adresář:** [`01_structured_extraction/`](./01_structured_extraction/)  
**Cíl:** Extrahovat z nestrukturovaného textu (e-mail, chat, **přepis hlasového hovoru**) strukturovaný JSON pomocí LLM + Pydantic.  
**Klíčové dovednosti:** structured outputs, Pydantic schémata, ošetření chyb, normalizace dat z ASR (čísla diktovaná slovy).  
**Webové UX:** ne (čistě batch processing).  
**Voice relevance:** ⭐⭐⭐ — typický first-step v každém voicebotu (porozumění tomu, co uživatel chce).

---

### 02 - RAG FAQ Bot
**Adresář:** [`02_rag_faq_bot/`](./02_rag_faq_bot/)  
**Cíl:** Interní HR asistent nad příručkou. Žádné halucinace, dual mode (chat + voice).  
**Klíčové dovednosti:** RAG pipeline (chunking, embedding, retrieval), prompt engineering proti halucinacím, voice constraints (krátké odpovědi pro TTS).  
**Webové UX:** doporučeno — FastAPI + vanilla HTML/JS s Web Speech API (`webkitSpeechRecognition` pro STT, `speechSynthesis` pro TTS, oba s `lang = 'cs-CZ'`).  
**Voice relevance:** ⭐⭐⭐ — klasický RAG use case pro konverzační systémy.

---

### 03 - Tool Calling Agent
**Adresář:** [`03_tool_calling_agent/`](./03_tool_calling_agent/)  
**Cíl:** Konverzační agent pro rezervaci stolů v restauraci, voice-aware s repair strategií a confirmation patterns.  
**Klíčové dovednosti:** Function Calling / Tool Calling, state management (LangGraph nebo čistý cyklus), repair patterns pro ASR errory, confirmation pattern před destruktivní akcí.  
**Webové UX:** doporučeno — FastAPI + JS s push-to-talk Web Speech API + debug panel s tool calls.  
**Voice relevance:** ⭐⭐⭐⭐⭐ — jádro role AI Agent Developer.

---

### 04 - LLM Evaluator (LLM-as-a-Judge)
**Adresář:** [`04_llm_evaluator/`](./04_llm_evaluator/)  
**Cíl:** Automatická evaluace voicebot konverzací silnějším LLM podle metrik (politeness, efficiency, **voice suitability**).  
**Klíčové dovednosti:** prompt engineering pro konzistentní hodnocení, Pydantic pro strukturované evaluační výstupy, agregace přes dávku, self-consistency / few-shot.  
**Webové UX:** ne (batch evaluace), volitelně HTML report.  
**Voice relevance:** ⭐⭐⭐⭐ — iterativní zlepšování na základě analýzy konverzačního provozu.

---

### 05 - Voicebot HR Screening — **CAPSTONE**
**Adresář:** [`05_voicebot_hr_screening/`](./05_voicebot_hr_screening/)  
**Cíl:** Outbound voicebot pro předkvalifikační HR rozhovor.  
**Klíčové dovednosti:** **conversation design jako disciplína**, state machine (LangGraph), confirmation pattern, voice constraints, **Czech-specific** (skloňování, čísla pro TTS, vykání/tykání), end-to-end voice-first UX.  
**Webové UX:** povinně — FastAPI + JS s push-to-talk, barge-in (`speechSynthesis.cancel()`), live transkript, výsledný `KandidateProfile`.  
**Voice relevance:** ⭐⭐⭐⭐⭐ — capstone projekt spojující všechny předchozí dovednosti.

---

## Doporučené pořadí

### Pro učení (čas neomezen)
**#03 → #02 → #05 → #01 → #04**

Začněte tool callingem (jádro role), pak RAG, pak capstone, pak doplňkové dovednosti.

### Pro rychlou ukázku (omezený čas)
**#03 → #05** (zkrácená verze)

Tool calling + capstone voicebot jsou nejpraktičtější jádro demonstrace.

### Pokud chcete cvičit do hloubky
Pro každý projekt udělejte i sekci **co bych dělal jinak při retry** v `report.md`. Nutí to k retrospektivě.

## Společný stack a setup

### Backend
- Python 3.11+
- `openai` (nebo `anthropic`) — LLM klient
- `pydantic` — strukturované výstupy
- `fastapi` + `uvicorn` — webové API (pro projekty s UX)
- `pytest` — testy
- (volitelně) `langgraph` — state machines pro agenty
- (volitelně) `chromadb` nebo `faiss` — vector DB pro RAG

### Frontend (kde relevantní)
- Vanilla HTML + JS (žádný framework, žádný build).
- **Web Speech API** v Chrome:
  - `webkitSpeechRecognition` (STT) — vyžaduje `webkit` prefix.
  - `speechSynthesis` + `SpeechSynthesisUtterance` (TTS).
  - Oba podporují `lang = 'cs-CZ'`, ale kvalita českého TTS hlasu závisí na OS (Windows/Mac obvykle lepší než Linux).

### Doporučená společná struktura

```
NN_project_name/
├── doc/project-progress/
│   ├── brief.md       (zadání - hotovo)
│   ├── spec.md        (vaše specifikace - psát ručně)
│   └── report.md      (vaše retrospektiva po dokončení)
├── app/
│   ├── server.py      (FastAPI)
│   ├── agent/         (core LLM logika)
│   └── prompts/       (system prompty jako .md soubory)
├── static/
│   ├── index.html
│   └── app.js
├── tests/
├── pyproject.toml
└── .env.example       (OPENAI_API_KEY=...)
```

## Volba LLM modelu

Pro tyto projekty potřebujete LLM se solidním **tool callingem** a **structured outputs**. Tady je krátký přehled relevantních možností (květen 2026).

### Cloudové modely (doporučené pro skutečnou práci)

| Model | Vendor | Cena $/1M (in/out) | Tool calling | Poznámka |
|---|---|---|---|---|
| `gpt-4o-mini` | OpenAI | 0.15 / 0.60 | ⭐⭐⭐⭐ | Nejlevnější rozumný model. Strict structured outputs. |
| `gemini-3.5-flash` | Google | 1.50 / 9.00 | ⭐⭐⭐⭐⭐ | **Nově (19.5.2026).** 1M context, multimodal, free tier. Výrazně lepší tool calling než GPT-4o-mini. |
| `claude-haiku-4.5` | Anthropic | 1.00 / 5.00 | ⭐⭐⭐⭐ | XML tagy, tone-sensitive. Dobrý pro konverzační agenty. |
| `gpt-4o` / `gpt-5.5` | OpenAI | 2.50 / 10 | ⭐⭐⭐⭐⭐ | Pro LLM-as-Judge v projektu #04. |
| `claude-sonnet-4.6` | Anthropic | 3.00 / 15 | ⭐⭐⭐⭐⭐ | Alternativa k GPT-5.5 jako judge. |

**Doporučení:** pro běžnou práci `gpt-4o-mini` (nejlevnější) nebo `gemini-3.5-flash` (zdarma do limitů free tieru, lepší tool calling). Pro evaluator (#04) silnější model.

### Lokální modely (offline experimenty bez nákladů, přes Ollama)

Vhodné pro `LLM_BACKEND=ollama` v `src/examples/agent_patterns/orig/llm_client.py`. Předpoklad: notebook bez dedikované GPU.

| Model | RAM (Q4) | Tok/s na CPU | Tool calling | Pro koho |
|---|---|---|---|---|
| `qwen3:8b` | ~5 GB | 1-4 | ⭐⭐⭐⭐ | **Default volba.** Drop-in upgrade `qwen2.5:7b-instruct`. |
| `qwen3:14b` | ~9 GB | 0.5-2 | ⭐⭐⭐⭐ | Pro 32GB+ RAM, lepší reasoning. |
| `qwen2.5:1.5b` | ~1 GB | 5-15 | ⭐⭐⭐ | Pro chat-like UX, kde latence bolí. |
| `gemma4:26b-a4b` (MoE) | ~16 GB | běží jako 4B | ⭐⭐ | Multimodal, ale slabší tool calling. |
| `llama3.1:8b` | ~5 GB | 1-4 | ⭐⭐⭐⭐ | Alternativa k Qwen3, lepší TTFT. |

**Doporučení:** `qwen3:8b` jako default. Na CPU je 7-8B model na hraně použitelnosti pro chat (5-15 sekund/odpověď), proto pro reálnou práci raději cloud.

### Přepínání mezi backendy

V kódu mějte společný klient s env var:

```python
def make_client() -> tuple[OpenAI, str]:
    backend = os.getenv("LLM_BACKEND", "openai").lower()
    if backend == "openai":
        return OpenAI(), os.getenv("LLM_MODEL", "gpt-4o-mini")
    if backend == "gemini":
        # Gemini má OpenAI-compatible endpoint
        return (
            OpenAI(
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                api_key=os.environ["GEMINI_API_KEY"],
            ),
            os.getenv("LLM_MODEL", "gemini-3.5-flash"),
        )
    # default: ollama
    return (
        OpenAI(base_url="http://localhost:11434/v1", api_key="ollama-local"),
        os.getenv("LLM_MODEL", "qwen3:8b"),
    )
```

Pak `LLM_BACKEND=gemini python script.py` pro experimenty bez OpenAI kreditu.

## Jak používat AI při řešení
Viz samostatný dokument [`How_to_use_AI_in_programming-recommendations.md`](./How_to_use_AI_in_programming-recommendations.md).

**Stručně:** návrh architektury, prompty, agent loop a Pydantic schémata pište ručně (RED zone). Boilerplate (FastAPI, frontend, konfigurace) můžete delegovat na AI (GREEN zone). Implementaci core logiky pair-programujte s AI (YELLOW zone).

## Související materiály

- [`agent_patterns/`](../examples/agent_patterns/) — LangGraph, tool calling teorie a tutoriály (agentflow vs. reference implementace).

## Pozn. ke zdroji briefů
Briefy v jednotlivých projektech (`brief.md`) byly iniciálně vygenerovány Gemini 3.5 Pro, následně revidovány a doplněny o **voice constraints, ASR error handling, confirmation patterns a Czech-specific challenges**.
