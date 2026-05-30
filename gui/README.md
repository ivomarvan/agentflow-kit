# agentflow GUI

Web-based interface for any `AgentApp` instance. Built with Vue 3 + Vite + PrimeVue.

## Development

Start backend first:

```bash
uv run python examples/quickstart/04_parallel_research_loop.py gui --no-browser
```

Then start frontend dev server (hot reload):

```bash
cd gui
npm install
npm run dev
# Opens on http://localhost:5173, proxied to FastAPI on :8765
```

## Build (production)

```bash
cd gui
npm run build
cp -r dist/. ../agentflow/gui/static/
```

The built output in `agentflow/gui/static/` is committed to git (users don't need Node.js).

## Adding custom event renderers

1. Create `my_event.vue` in `gui/src/event-renderers/`
2. Register it in `gui/src/event-renderers/index.ts`:

   ```typescript
   import MyEvent from './my_event.vue'
   export const EVENT_RENDERERS = {
     "my.event": MyEvent,
   }
   ```

3. Rebuild: `npm run build && cp -r dist/. ../agentflow/gui/static/`

## Notes

- **Dev/demo tool only** — no authentication, single user, localhost only
- Requires Chrome/Edge for VoiceBot (Web Speech API)
- Port: default 8765, override via `AGENTFLOW_GUI_PORT` env or `--port` CLI
