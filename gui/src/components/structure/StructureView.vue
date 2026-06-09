<template>
  <div class="structure-view">
    <div v-if="loading" class="loading">
      <i class="pi pi-spin pi-spinner" /> Loading graph…
    </div>

    <iframe
      v-else-if="structureStore.graphHtml"
      class="graph-frame"
      :srcdoc="structureStore.graphHtml"
      sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"
      title="Agent structure graph"
      @load="onGraphFrameLoad"
    />

    <div v-else class="empty-state">
      Graph not available.
    </div>

    <!-- Global tooltip overlay: rendered outside iframe via postMessage bridge -->
    <Teleport to="body">
      <div
        v-show="tooltipVisible"
        ref="tooltipEl"
        class="gv-parent-tooltip"
        :class="{ sticky: tooltipFrozen }"
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

// --- iframe tooltip overlay ---
const tooltipEl = ref<HTMLElement | null>(null)
const tooltipVisible = ref(false)
const tooltipFrozen = ref(false)
const tooltipHtml = ref('')
const tooltipStyle = ref({ left: '0px', top: '0px' })

let tooltipSource: string | null = null
let hideTimer: ReturnType<typeof setTimeout> | null = null
let idleTimer: ReturnType<typeof setTimeout> | null = null
const TT_OFFSET_X = 14
const TT_OFFSET_Y = 8
const TT_HIDE_MS = 300
const TT_IDLE_MS = 700

function clearHide() { if (hideTimer) { clearTimeout(hideTimer); hideTimer = null } }
function clearIdle() { if (idleTimer) { clearTimeout(idleTimer); idleTimer = null } }

function hideTooltip() {
  clearHide(); clearIdle()
  tooltipVisible.value = false
  tooltipFrozen.value = false
  tooltipSource = null
}

function scheduleHideTooltip() {
  clearHide()
  hideTimer = setTimeout(hideTooltip, TT_HIDE_MS)
}

function freezeTooltip() { tooltipFrozen.value = true }

function armIdleTooltip() {
  clearIdle()
  idleTimer = setTimeout(freezeTooltip, TT_IDLE_MS)
}

function placeTooltip(iframeClientX: number, iframeClientY: number) {
  const iframe = graphIframe()
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

function onTooltipEnter() { clearHide(); freezeTooltip() }
function onTooltipLeave() { hideTooltip() }

// --- graph iframe helpers ---
function graphIframe(): HTMLIFrameElement | null {
  return document.querySelector('iframe.graph-frame')
}

function postGraphHighlight(nodeId: string | null) {
  graphIframe()?.contentWindow?.postMessage(
    { type: 'af:highlightNode', nodeId: nodeId ?? '' },
    '*',
  )
}

function onGraphFrameLoad() {
  postGraphHighlight(structureStore.selectedNode)
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
      scheduleHideTooltip()
      return
    }

    if (action === 'show' && md) {
      const src = md.slice(0, 80)  // use snippet as stable source id
      if (tooltipSource !== src) {
        tooltipSource = src
        tooltipHtml.value = marked.parse(md) as string
        tooltipFrozen.value = false
        tooltipVisible.value = true
        if (x !== undefined && y !== undefined) placeTooltip(x, y)
      }
      clearHide()
      if (!tooltipFrozen.value) armIdleTooltip()
      return
    }

    if (action === 'move' && x !== undefined && y !== undefined) {
      if (!tooltipVisible.value || tooltipFrozen.value) return
      placeTooltip(x, y)
      armIdleTooltip()
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
}
.loading,
.empty-state {
  padding: 2rem;
  text-align: center;
}
.graph-frame {
  width: 100%;
  height: 100%;
  min-height: 320px;
  border: 1px solid var(--p-content-border-color, #e2e8f0);
  border-radius: 8px;
  background: #f0f2f5;
}

/* --- Graph tooltip overlay (rendered via Teleport to <body>) --- */
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
  pointer-events: none;
}
.gv-parent-tooltip.sticky {
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
