<template>
  <div class="structure-view">
    <div class="structure-toolbar">
      <span class="hint">Click on a node to view its settings</span>
    </div>

    <div v-if="loading" class="loading">
      <i class="pi pi-spin pi-spinner" /> Loading graph…
    </div>

    <div
      v-else-if="structureStore.svgContent"
      class="graph-container"
      ref="graphEl"
      v-html="structureStore.svgContent"
      @click="onGraphClick"
    />

    <div v-else class="empty-state">
      Graph not available.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { api } from '@/services/api'
import { useStructureStore } from '@/stores/structure'

const emit = defineEmits<{ (e: 'nodeClick', nodeId: string): void }>()

const loading = ref(true)
const graphEl = ref<HTMLElement | null>(null)
const structureStore = useStructureStore()

onMounted(async () => {
  try {
    const svg = await api.getGraph()
    structureStore.setSvg(svg)
    await nextTick()
    addNodeStyles()
  } catch (e) {
    console.error('Failed to load graph', e)
  } finally {
    loading.value = false
  }
})

/** Add pointer cursor to all Graphviz node elements for click affordance. */
function addNodeStyles() {
  if (!graphEl.value) return
  graphEl.value.querySelectorAll('g.node').forEach((node) => {
    ;(node as HTMLElement).style.cursor = 'pointer'
  })
}

/** Delegate click to the nearest Graphviz node group and extract its title. */
function onGraphClick(e: MouseEvent) {
  const target = e.target as Element
  const nodeGroup = target.closest('g.node')
  if (!nodeGroup) return
  // Graphviz SVG uses <title> as the first child of each node group
  const title = nodeGroup.querySelector('title')?.textContent?.trim()
  if (!title) return
  structureStore.selectNode(title)
  emit('nodeClick', title)
}
</script>

<style scoped>
.structure-view { padding: 1rem; }
.structure-toolbar { margin-bottom: 1rem; }
.hint { font-size: 0.85rem; color: var(--p-text-muted-color, #888); }
.loading, .empty-state { padding: 2rem; text-align: center; }
.graph-container {
  overflow: auto;
  border: 1px solid var(--p-content-border-color, #e2e8f0);
  border-radius: 8px;
  padding: 1rem;
  max-height: calc(100vh - 200px);
}
/* SVG node hover highlight */
.graph-container :deep(g.node:hover ellipse),
.graph-container :deep(g.node:hover polygon),
.graph-container :deep(g.node:hover rect) {
  fill: var(--p-primary-100, #e0e7ff) !important;
  stroke: var(--p-primary-500, #6366f1) !important;
}
</style>
