<template>
  <div class="ap-panel">
    <div class="ap-header">API Actions</div>
    <div v-if="loading" class="ap-loading">Loading tools…</div>
    <div v-else-if="error" class="ap-error">{{ error }}</div>
    <ActionForm
      v-else
      v-for="tool in tools"
      :key="tool.name"
      :tool="tool"
      @action-result="onResult"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import ActionForm from '@/components/demo/ActionForm.vue'
import { useDemoStore } from '@/stores/demo'
import { storeToRefs } from 'pinia'

const demoStore = useDemoStore()
const { tools } = storeToRefs(demoStore)
const loading = ref(true)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    await demoStore.loadTools()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
})

function onResult() {
  // StateViewerPanel updates via WebSocket state_update events.
}
</script>

<style scoped>
.ap-panel {
  height: 100%;
  overflow-y: auto;
  padding: 0.5rem;
}
.ap-header {
  font-weight: 700;
  margin-bottom: 0.75rem;
  font-size: 0.95rem;
}
.ap-loading,
.ap-error {
  font-size: 0.85rem;
  color: var(--p-text-muted-color, #64748b);
}
.ap-error {
  color: #b91c1c;
}
</style>
