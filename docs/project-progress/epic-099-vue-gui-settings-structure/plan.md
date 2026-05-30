---
apm_category: epic-plan
apm_ref: E099
apm_level: epic
created_by: Planner
model: claude-sonnet-4-6
intended_for: Coder
created_at: 2026-05-30
updated_at: 2026-05-30
approved_by: Human
approved_at: 2026-05-30
---

# Epic E099 — Vue GUI: Settings + Structure (kombinovaný panel)

**Cíl:** Implementovat záložky **Settings** a **Structure** v GUI. Obě záložky jsou
propojeny: kliknutí na vrchol grafu (Structure) scrolluje a zvýrazní příslušnou sekci
v editoru parametrů (Settings). Parametry editovatelné za běhu přes `AgentApp.set_config()`.

---

## Scope

| Oblast | Co se mění |
|--------|-----------|
| `gui/src/components/settings/` (nový) | Hierarchický editor parametrů |
| `gui/src/components/structure/` (nový) | SVG graph + klik na vrchol |
| `gui/src/App.vue` | Aktivovat záložky Settings, Structure |
| `@jsonforms/vue` | Renderování JSON Schema formuláře |
| `agentflow/gui/server.py` | Endpointy `/api/schema`, `/api/config` (z E097, ověřit) |

---

## Task List

| Task | Název | Závisí na |
|------|-------|-----------|
| T010 | Settings záložka: @jsonforms/vue hierarchický editor | E097, E098 |
| T020 | Structure záložka: SVG graf + klik handler | E098 |
| T030 | Propojení: klik na vrchol → scroll v Settings | T010, T020 |
| T040 | Aktivace záložek v App.vue + live set_config() | T030 |

---

## T010 — Settings záložka

### Instalace

```bash
npm install @jsonforms/vue @jsonforms/vue-vanilla @jsonforms/core
```

### Komponenty

```
src/components/settings/
    SettingsView.vue        ← hlavní záložka
    ParamGroup.vue          ← sekce (connector, graph, agent...)
    ParamField.vue          ← jeden parametr (label + input)
```

### `SettingsView.vue`

```html
<template>
  <div class="settings-view">
    <json-forms
      :data="configValues"
      :schema="configSchema"
      :uischema="uiSchema"
      :renderers="renderers"
      @change="onChange"
    />
    <Button label="Apply" @click="applyChanges" :disabled="!hasChanges" />
    <Button label="Reset" @click="resetChanges" severity="secondary" />
  </div>
</template>
```

`onChange` ukládá do lokálního draft; **Apply** zavolá `POST /api/config` pro každou
změněnou hodnotu. `Reset` zahodí draft.

### Poznámka o @jsonforms/vue

Po MVP zvážit refaktoring na custom rekurzivní komponentu `ParamTreeEditor.vue`
(lepší kontrola nad UI, zejména pro propojení se Structure záložkou).
Tato poznámka bude v `gui/README.md`.

---

## T020 — Structure záložka

### Instalace

```bash
npm install d3 @types/d3
# d3-graphviz vyžaduje @hpcc-js/wasm (graphviz WASM)
npm install d3-graphviz @hpcc-js/wasm
```

### Komponenty

```
src/components/structure/
    StructureView.vue       ← hlavní záložka
    GraphCanvas.vue         ← d3-graphviz SVG kontejner
```

### `GraphCanvas.vue`

```typescript
// Načte DOT z /api/graph?format=dot, renderuje přes d3-graphviz
// Po renderu přidá click handlery na <g class="node"> elementy
graphviz("#graph-container")
    .renderDot(dotSource)
    .on("end", () => {
        d3.selectAll("g.node").on("click", (event, d) => {
            emit("nodeClick", d.key)  // d.key = název vrcholu
        })
    })
```

Alternativa: FastAPI servuje SVG přímo (`GET /api/graph?format=svg`); JavaScript přidá
inline click handlery na `<g>` elementy. Toto je jednodušší — nevyžaduje `d3-graphviz`.

---

## T030 — Propojení: klik na vrchol → Settings

### Komunikace Settings ↔ Structure

Pinia store `useStructureStore`:
```typescript
const selectedNode = ref<string | null>(null)

function selectNode(nodeId: string) {
    selectedNode.value = nodeId
    // event pro Settings tab
    bus.emit('node-selected', nodeId)
}
```

V `SettingsView.vue`:
```typescript
watch(selectedNode, (nodeId) => {
    if (nodeId) scrollToParam(nodeId)  // smooth scroll + highlight
})
```

`scrollToParam()` mapuje `nodeId` (název vrcholu) na dot-path v config schema a scrolluje
na příslušný `<section>` v editoru.

### Vizuální feedback

- Kliknutý vrchol v grafu: přidá CSS class `selected` (border highlight)
- Příslušná sekce v Settings: scroll + 2s highlight animace

---

## T040 — Live set_config() + aktivace záložek

### Live vs. batch update

- **Batch (Apply button)**: bezpečnější — uživatel vidí co změní, pak potvrdí
- **Live (při onChange)**: pohodlnější pro jednoduché hodnoty (temperature slider)

Implementace: checkbox v Settings `"Apply changes immediately"` (default OFF = batch).

### `App.vue` — aktivace záložek

```html
<Tabs>
    <TabPanel value="chat">      <ChatView />     </TabPanel>
    <TabPanel value="settings">  <SettingsView /> </TabPanel>  <!-- aktivováno -->
    <TabPanel value="structure"> <StructureView/> </TabPanel>  <!-- aktivováno -->
</Tabs>
```

---

## Epic E099 Definition of Done

- [ ] Settings záložka zobrazí JSON Schema formulář z `GET /api/schema`
- [ ] `Apply` zavolá `POST /api/config` pro každou změnu
- [ ] `Reset` obnoví původní hodnoty
- [ ] Structure záložka zobrazí SVG graf AgentApp
- [ ] Kliknutí na vrchol grafu aktivuje záložku Settings a scrolluje na parametry
- [ ] Zvýrazňovací animace při skoku na parametr
- [ ] Pre-built dist aktualizován a commitnut
- [ ] `gui/README.md` aktualizován

## Post-MVP poznámka (z diskuze s uživatelem)

Po realizaci zvážit nahrazení `@jsonforms/vue` vlastní `ParamTreeEditor.vue` komponentou
pro lepší propojení s grafem (klik na vrchol → přesný scroll na příslušný param, ne jen sekci).
