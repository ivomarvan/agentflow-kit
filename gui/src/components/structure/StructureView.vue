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
    />

    <div v-else class="empty-state">
      Graph not available.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@/services/api'
import { useStructureStore } from '@/stores/structure'

const loading = ref(true)
const structureStore = useStructureStore()

onMounted(async () => {
  try {
    const html = await api.getGraph()
    structureStore.setGraphHtml(html)
  } catch (e) {
    console.error('Failed to load graph', e)
  } finally {
    loading.value = false
  }
})
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
</style>
