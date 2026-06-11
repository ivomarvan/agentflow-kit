<template>
  <div class="structure-view">
    <div v-if="loading" class="loading">
      <i class="pi pi-spin pi-spinner" /> Loading graph…
    </div>

    <template v-else-if="structureStore.graphHtml">
      <!-- Zoom toolbar — floats above the scroll area -->
      <div class="zoom-toolbar">
        <button class="zoom-btn" @click="zoomOut" :disabled="zoom <= ZOOM_MIN" title="Zoom out">−</button>
        <button class="zoom-btn zoom-reset" @click="zoomReset" title="Reset zoom &amp; center">⌂</button>
        <button class="zoom-btn" @click="zoomIn"  :disabled="zoom >= ZOOM_MAX" title="Zoom in">+</button>
        <span class="zoom-label">{{ Math.round(zoom * 100) }}%</span>
      </div>

      <!--
        graph-scroll   — scrollable viewport (overflow:auto); scrollbars appear here
        zoom-wrapper   — layout placeholder whose size = natural × zoom;
                         this is what the scroll container measures to decide whether
                         to show scrollbars
        iframe         — renders at natural size; CSS transform:scale() zooms it visually
      -->
      <div class="graph-scroll" ref="scrollEl">
        <div ref="wrapperEl" class="zoom-wrapper">
          <iframe
            ref="frameEl"
            class="graph-frame"
            :srcdoc="structureStore.graphHtml"
            sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
            title="Agent structure graph"
            @load="onGraphFrameLoad"
          />
        </div>
      </div>
    </template>

    <div v-else class="empty-state">
      Graph not available.
    </div>

    <!-- Global tooltip overlay: rendered outside iframe via postMessage bridge -->
    <Teleport to="body">
      <div
        v-show="tooltipVisible"
        ref="tooltipEl"
        class="gv-parent-tooltip"
        :style="tooltipStyle"
        v-html="tooltipHtml"
        @mouseenter="onTooltipEnter"
        @mouseleave="onTooltipLeave"
      />
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { marked } from 'marked'
import { api } from '@/services/api'
import { useStructureStore } from '@/stores/structure'

const loading = ref(true)
const structureStore = useStructureStore()

// --- DOM refs ---
const scrollEl  = ref<HTMLElement | null>(null)
const wrapperEl = ref<HTMLElement | null>(null)
const frameEl   = ref<HTMLIFrameElement | null>(null)

// --- Zoom ---
const ZOOM_MIN  = 0.5
const ZOOM_MAX  = 4.0
const ZOOM_STEP = 0.25
const zoom      = ref(1.0)

/**
 * Apply zoom using the CSS transform + layout-wrapper technique.
 *
 * The iframe always renders at the natural (container) size so the SVG inside
 * auto-fits correctly.  A CSS transform:scale() zooms it visually while a
 * wrapper div with explicit pixel dimensions (natural × zoom) tells the scroll
 * container how large the scrollable area is.
 *
 * This is the canonical browser pattern used by PDF viewers, Figma, etc.
 */
function applyZoom(z: number) {
  const frame     = frameEl.value
  const wrapper   = wrapperEl.value
  const container = scrollEl.value
  if (!frame || !wrapper || !container) return

  if (z === 1.0) {
    // Natural fit — remove all explicit overrides
    wrapper.style.width  = ''
    wrapper.style.height = ''
    frame.style.width     = ''
    frame.style.height    = ''
    frame.style.transform = ''
    container.scrollTop  = 0
    container.scrollLeft = 0
    return
  }

  // Natural dimensions = current visible size of the scroll container.
  // clientWidth/clientHeight exclude scrollbars and give the visible area.
  const nW = container.clientWidth
  const nH = container.clientHeight

  // Wrapper: sets the scrollable area that overflow:auto measures.
  wrapper.style.width  = Math.round(nW * z) + 'px'
  wrapper.style.height = Math.round(nH * z) + 'px'

  // iframe: renders at natural size, then scaled visually via CSS transform.
  // transform:scale() does NOT affect layout — it only affects rendering.
  // The wrapper's explicit dimensions compensate for this.
  frame.style.width          = nW + 'px'
  frame.style.height         = nH + 'px'
  frame.style.transform      = `scale(${z})`
  frame.style.transformOrigin = 'top left'
}

function zoomIn() {
  zoom.value = Math.min(ZOOM_MAX, Math.round((zoom.value + ZOOM_STEP) * 100) / 100)
  applyZoom(zoom.value)
}

function zoomOut() {
  zoom.value = Math.max(ZOOM_MIN, Math.round((zoom.value - ZOOM_STEP) * 100) / 100)
  applyZoom(zoom.value)
}

function zoomReset() {
  zoom.value = 1.0
  applyZoom(1.0)
}

// --- iframe tooltip overlay ---
const tooltipEl      = ref<HTMLElement | null>(null)
const tooltipVisible = ref(false)
const tooltipHovered = ref(false)
const tooltipHtml    = ref('')
const tooltipStyle   = ref({ left: '0px', top: '0px' })

let tooltipSource: string | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null
const TT_OFFSET_X = 14
const TT_OFFSET_Y = 8
const TT_HIDE_MS  = 300

function clearHide() { if (hideTimer) { clearTimeout(hideTimer); hideTimer = null } }

function hideTooltip() {
  clearHide()
  tooltipVisible.value = false
  tooltipSource        = null
}

function scheduleHideTooltip() {
  clearHide()
  hideTimer = setTimeout(hideTooltip, TT_HIDE_MS)
}

function placeTooltip(iframeClientX: number, iframeClientY: number) {
  const iframe = frameEl.value
  if (!iframe) return
  const rect = iframe.getBoundingClientRect()
  const absX = rect.left + iframeClientX + TT_OFFSET_X
  const absY = rect.top  + iframeClientY + TT_OFFSET_Y
  const w = tooltipEl.value?.offsetWidth || 420
  const left = (absX + w > window.innerWidth) ? (rect.left + iframeClientX - w - 4) : absX
  tooltipStyle.value = {
    left: `${Math.max(0, left)}px`,
    top:  `${Math.max(8, absY)}px`,
  }
}

function onTooltipEnter() { tooltipHovered.value = true; clearHide() }
function onTooltipLeave() { tooltipHovered.value = false; scheduleHideTooltip() }

function postGraphHighlight(nodeId: string | null) {
  frameEl.value?.contentWindow?.postMessage(
    { type: 'af:highlightNode', nodeId: nodeId ?? '' },
    '*',
  )
}

function onGraphFrameLoad() {
  postGraphHighlight(structureStore.selectedNode)
  // Re-apply zoom after iframe content reload (srcdoc change resets styles)
  if (zoom.value !== 1.0) applyZoom(zoom.value)
}

function onIframeMessage(event: MessageEvent) {
  if (!event.data || typeof event.data !== 'object') return

  if (event.data.type === 'af:nodeClicked') {
    structureStore.selectNode(event.data.nodeId as string)
    return
  }

  if (event.data.type === 'af:tooltip') {
    const { action, md, x, y } = event.data as { action: string; md?: string; x?: number; y?: number }

    if (action === 'hide') {
      // Ignore hide requests from the iframe while the cursor is inside the panel —
      // the cursor already moved from the iframe into the tooltip panel.
      if (!tooltipHovered.value) scheduleHideTooltip()
      return
    }

    if (action === 'show' && md) {
      const src = md.slice(0, 80)
      if (tooltipSource !== src) {
        tooltipSource        = src
        tooltipHtml.value    = marked.parse(md) as string
        tooltipVisible.value = true
        if (x !== undefined && y !== undefined) placeTooltip(x, y)
      }
      clearHide()
      return
    }

    if (action === 'move' && x !== undefined && y !== undefined) {
      // Don't reposition while cursor is inside the panel.
      if (!tooltipVisible.value || tooltipHovered.value) return
      placeTooltip(x, y)
    }
  }
}

// Keep graph highlight in sync with shared selection (from either pane)
watch(
  [() => structureStore.selectedNode, () => structureStore.graphHtml],
  ([nodeId]) => {
    if (structureStore.graphHtml) postGraphHighlight(nodeId)
  },
)

onMounted(async () => {
  window.addEventListener('message', onIframeMessage)
  try {
    const html = await api.getGraph()
    structureStore.setGraphHtml(html)
  } catch (e) {
    console.error('Failed to load graph', e)
  } finally {
    loading.value = false
  }
})

onUnmounted(() => window.removeEventListener('message', onIframeMessage))
</script>

<style scoped>
.structure-view {
  padding: 0;
  height: 100%;
  position: relative;
  display: flex;
  flex-direction: column;
}
.loading,
.empty-state {
  padding: 2rem;
  text-align: center;
}

/* --- Zoom toolbar -------------------------------------------------- */
.zoom-toolbar {
  position: absolute;
  top: 8px;
  right: 10px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 2px;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--p-content-border-color, #d1d5db);
  border-radius: 8px;
  padding: 3px 6px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
  backdrop-filter: blur(4px);
}
.zoom-btn {
  width: 26px;
  height: 26px;
  border: none;
  background: transparent;
  border-radius: 5px;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 600;
  line-height: 1;
  color: var(--p-text-color, #374151);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.1s;
  padding: 0;
}
.zoom-btn:hover:not(:disabled) {
  background: var(--p-surface-100, #f3f4f6);
}
.zoom-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.zoom-reset { font-size: 0.9rem; }
.zoom-label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--p-text-muted-color, #6b7280);
  min-width: 2.6rem;
  text-align: center;
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, monospace;
}

/* --- Scroll container ---------------------------------------------- */
.graph-scroll {
  flex: 1;
  min-height: 0;
  min-width: 0;        /* prevent flex blowout in horizontal direction */
  overflow: auto;
}

/* --- Zoom wrapper (layout placeholder for scroll area size) --------- */
.zoom-wrapper {
  /* At zoom=1: fill the scroll container with no overflow */
  width: 100%;
  height: 100%;
  /* JS overrides width/height with nW*zoom × nH*zoom when zoom ≠ 1 */
}

/* --- Graph iframe -------------------------------------------------- */
.graph-frame {
  /* At zoom=1: fill the wrapper naturally */
  width: 100%;
  height: 100%;
  min-height: 320px;
  border: 1px solid var(--p-content-border-color, #e2e8f0);
  border-radius: 8px;
  background: #f0f2f5;
  display: block;  /* no inline-block gap */
  /* JS overrides width/height + adds transform:scale() when zoom ≠ 1 */
}

/* --- Graph tooltip overlay (rendered via Teleport to <body>) ------- */
.gv-parent-tooltip {
  position: fixed;
  z-index: 9999;
  max-width: 420px;
  max-height: 72vh;
  overflow-y: auto;
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 6px 28px rgba(0, 0, 0, 0.22);
  border-left: 4px solid #1976d2;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  font-size: 13px;
  line-height: 1.6;
  pointer-events: auto;
}
.gv-parent-tooltip :deep(h1),
.gv-parent-tooltip :deep(h2),
.gv-parent-tooltip :deep(h3) {
  font-weight: bold;
  margin: 0.5em 0 0.2em;
  color: #1976d2;
}
.gv-parent-tooltip :deep(h1) {
  font-size: 1.05rem;
  border-bottom: 1px solid #eee;
  padding-bottom: 4px;
}
.gv-parent-tooltip :deep(code) {
  background: #f0f4f8;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.88em;
}
.gv-parent-tooltip :deep(pre) {
  background: #f0f4f8;
  padding: 8px;
  border-radius: 4px;
  margin: 6px 0;
  overflow-x: auto;
}
.gv-parent-tooltip :deep(ul),
.gv-parent-tooltip :deep(ol) {
  padding-left: 1.4em;
  margin: 3px 0;
}
.gv-parent-tooltip :deep(li) { margin: 2px 0; }
.gv-parent-tooltip :deep(p)  { margin: 4px 0; }
.gv-parent-tooltip :deep(em) { color: #666; }
.gv-parent-tooltip :deep(strong) { color: #222; }
.gv-parent-tooltip :deep(a) {
  color: #1565c0;
  text-decoration: underline;
  pointer-events: auto;
  cursor: pointer;
}
</style>
