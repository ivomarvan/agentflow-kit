---
apm_category: epic-plan
apm_ref: E098
apm_level: epic
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-05-30
updated_at: 2026-05-30
approved_by: Human
approved_at: 2026-05-30
---

# Epic E098 — Vue GUI: Chat + Log panel (MVP)

**Cíl:** Vytvořit Vue 3 + Vite frontend v `gui/`. Záložka **Chat**: uživatel zadá prompt,
dostane výsledek z `AgentApp.run_workflow()`, v rozbalovacím panelu vidí real-time
log events přes WebSocket. Předpřipravené prompty ze `sample_prompts`. Conversation
history v lokálním Vue state.

Pre-built `gui/dist/` commitovaný do repozitáře; FastAPI z E097 ho servuje jako SPA.

---

## Scope

| Oblast | Co se mění |
|--------|-----------|
| `gui/` (nový adresář) | Vue 3 + Vite projekt |
| `gui/src/` | Komponenty, stores, API client |
| `gui/dist/` | Pre-built SPA — commitováno do gitu |
| `agentflow/gui/static/` | Symlink nebo kopie `gui/dist/` |
| `gui/README.md` (nový) | Jak vyvíjet a buildovat |

---

## Technologický stack

| Nástroj | Verze | Účel |
|---------|-------|------|
| Vue 3 | latest | Frontend framework |
| Vite | latest | Build tool + dev server |
| TypeScript | 5.x | Type safety |
| Pinia | latest | State management |
| PrimeVue | 4.x | UI component library |
| `@primevue/themes` | 4.x | Styling |

---

## Task List

| Task | Název | Závisí na |
|------|-------|-----------|
| T010 | Vite + Vue 3 project scaffold + PrimeVue setup | E097 |
| T020 | API client + WebSocket service | T010 |
| T030 | Chat záložka + Conversation history | T020 |
| T040 | Log panel (collapsible) + domain event renderers | T030 |
| T050 | Sample prompts chips + pre-built dist | T030, T040 |

---

## T010 — Scaffold

```
gui/
    package.json
    vite.config.ts
    tsconfig.json
    index.html
    src/
        main.ts
        App.vue                     ← tab navigation (Chat | Settings | Structure)
        components/
        stores/
        services/
        event-renderers/
            index.ts                ← event_type → Vue component registry
            GenericJsonRenderer.vue ← fallback
    dist/                           ← pre-built, commitováno
    README.md
```

### `vite.config.ts` proxy (pro vývoj)

```typescript
export default defineConfig({
    server: {
        proxy: {
            '/api': 'http://localhost:8765',
            '/ws':  { target: 'ws://localhost:8765', ws: true },
        }
    }
})
```

### `gui/README.md`

- Jak spustit v dev módu: `npm run dev` (Vite dev server na :5173, API proxy na :8765)
- Jak buildovat: `npm run build` → `dist/`
- Jak aktualizovat commitnutý build: `npm run build && cp -r dist/ ../agentflow/gui/static/`
- Jak přidat custom event renderer: vytvořit `src/event-renderers/my_event.vue`
  a registrovat v `index.ts`
- Poznámka o dev/demo charakteru (žádná autentizace)

---

## T020 — API client + WS service

### `src/services/api.ts`

```typescript
export interface RunInfo { run_id: string; status: "started" | "conflict" }
export interface AppInfo { name: string; description: string }
export interface ConfigSchema { schema: Record<string, unknown> }

export const api = {
    getInfo:    (): Promise<AppInfo>     => fetch('/api/info').then(r => r.json()),
    getSamples: (): Promise<string[]>    => fetch('/api/samples').then(r => r.json()),
    getGraph:   (): Promise<string>      => fetch('/api/graph').then(r => r.text()),
    getSchema:  (): Promise<ConfigSchema>=> fetch('/api/schema').then(r => r.json()),
    getConfig:  (): Promise<Record<string,unknown>> => fetch('/api/config').then(r => r.json()),
    setConfig:  (path: string, value: unknown): Promise<void> =>
        fetch('/api/config', { method: 'POST', body: JSON.stringify({path, value}), headers: {'Content-Type':'application/json'} }).then(() => {}),
    startRun:   (prompt: string): Promise<RunInfo> =>
        fetch('/api/run', { method: 'POST', body: JSON.stringify({prompt}), headers: {'Content-Type':'application/json'} }).then(r => r.json()),
}
```

### `src/services/wsClient.ts`

```typescript
export function connectEventStream(runId: string, onEvent: (msg: WsMessage) => void): () => void {
    const ws = new WebSocket(`ws://localhost:8765/ws/${runId}`)
    // ... reconnect logic, close on cleanup
    return () => ws.close()
}
```

---

## T030 — Chat záložka

### Komponenty

```
src/components/chat/
    ChatView.vue            ← hlavní záložka
    MessageBubble.vue       ← jedna zpráva (user | assistant)
    ConversationHistory.vue ← scrollovatelný seznam zpráv
    PromptInput.vue         ← textarea + Send button + stav "running"
```

### Conversation history

Pinia store `useChatStore`:
```typescript
interface Message {
    id: string
    role: 'user' | 'assistant'
    content: string
    result: string | null   // run_workflow() return value
    timestamp: Date
    run_id: string
    events: WsMessage[]     // pro log panel
}
```

Ukládá se v paměti prohlížeče (Vue reactive). Refresh = reset.

### UX chování

- `Send` button disabled pokud `isRunning` nebo input prázdný
- Při `POST /api/run` vrátí 409 → zobrazit "Run in progress, please wait"
- `assistant` bubublina zobrazuje `run_complete.result` nebo "Completed."
- Indikátor průběhu: spinner + "Running..." pokud WS stream aktivní

---

## T040 — Log panel + event renderers

### Collapsible log panel

```
src/components/chat/
    EventLogPanel.vue       ← rozbalovací panel pod každou zprávou
    EventLogEntry.vue       ← jedna řádka logu
```

Každá `Message` má vlastní `events[]`. Panel je collapsed by default, header zobrazí
počet událostí.

### Domain event display

```
src/event-renderers/
    index.ts                ← { "hotel.reservation": HotelReservation, ... }
    GenericJsonRenderer.vue ← fallback pro unknown event_type
```

`GenericJsonRenderer.vue` zobrazí formátovaný JSON (pre + syntax highlight).

`EventLogEntry.vue` dynamicky vybírá komponentu:
```html
<component
    :is="EVENT_RENDERERS[event.event_type] ?? GenericJsonRenderer"
    :event="event"
/>
```

Tato záložka/sekce je dokumentována v `gui/README.md` — jak přidat custom renderer.

---

## T050 — Sample prompts chips + pre-built dist

### Sample prompts

Chips/badges pod `PromptInput` — načteny z `GET /api/samples`. Klik vyplní input.
Pokud `sample_prompts` je prázdný → chips se nezobrazí.

### Pre-built dist

Po dokončení T040:
```bash
cd gui && npm run build
cp -r dist/* ../agentflow/gui/static/
git add agentflow/gui/static/
```

`agentflow/gui/static/` je commitnuto v git (jako Jupyter, Streamlit atd.).
`.gitignore` NEPŘIDÁVÁ `agentflow/gui/static/` — je to distribuovaný artefakt.

### Build check refresh

Při `ensure_build()` v `build.py` (z E097): pokud `static/` je starší než `gui/src/`:
```
GUI may be outdated. Rebuild? [Y/n]:
```

---

## Epic E098 Definition of Done

- [ ] `cd gui && npm run dev` spustí Vite na :5173 s proxy na :8765
- [ ] `python script.py gui` → FastAPI servuje Chat tab v browseru
- [ ] Uživatel zadá prompt → vidí výsledek v conversation history
- [ ] Log panel se rozbalí a zobrazí step events z WebSocket
- [ ] Domain event s unknown `event_type` zobrazí GenericJsonRenderer (formátovaný JSON)
- [ ] Sample prompts chips funkční (pokud `sample_prompts` neprázdný)
- [ ] `gui/dist/` commitnuto, FastAPI ho servuje
- [ ] `gui/README.md` popisuje dev workflow + custom renderers

## Poznámky pro Codera

- PrimeVue 4 — použít `pt` (PassThrough) pro CSS customizaci komponent
- `App.vue` obsahuje `<Tabs>` s `<TabPanel label="Chat">`, `<TabPanel label="Settings" disabled>`,
  `<TabPanel label="Structure" disabled>` — disabled záložky viditelné ale nefunkční (připraveno pro E099)
- WebSocket reconnect: pokud server restartuje, klient se znovu připojí (max 3 pokusy)
- CORS: FastAPI musí mít `CORSMiddleware` pro dev (`allow_origins=["http://localhost:5173"]`)

## Po dokončení E098 — revize plánu

Před zahájením E099 provést review:
- Je Chat tab použitelný na `04_parallel_research_loop`?
- Jsou log events dostatečně informativní?
- Jsou potřeba změny v EventBus/WS protokolu?
