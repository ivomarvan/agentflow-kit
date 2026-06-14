<template>
  <div class="demo-view-root">
    <div class="demo-top-row">
      <StickyMarkdownTooltipTitle
        :title="appInfo?.name ?? 'LiveModel Demo'"
        :doc="appInfo?.doc ?? ''"
      />
    </div>
    <Splitter layout="horizontal" class="demo-splitter">
      <SplitterPanel :size="35" :minSize="20" class="demo-pane">
        <ActionPanel />
      </SplitterPanel>
      <SplitterPanel :size="65" :minSize="30" class="demo-pane">
        <StateViewerPanel />
      </SplitterPanel>
    </Splitter>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { Splitter, SplitterPanel } from 'primevue'
import ActionPanel from '@/components/demo/ActionPanel.vue'
import StateViewerPanel from '@/components/stateviewer/StateViewerPanel.vue'
import StickyMarkdownTooltipTitle from '@/components/ui/StickyMarkdownTooltipTitle.vue'
import { api } from '@/services/api'
import { connectDemoEventStream } from '@/services/wsClient'
import { useDemoStore } from '@/stores/demo'
import { useStateViewerStore } from '@/stores/stateViewer'

const appInfo = ref<{ name: string; doc: string } | null>(null)
const demoStore = useDemoStore()
const svStore = useStateViewerStore()
let disconnectWs: (() => void) | null = null

onMounted(async () => {
  try {
    appInfo.value = await api.getInfo()
  } catch {
    // server not ready
  }
  await demoStore.loadLiveState()
  disconnectWs = connectDemoEventStream((msg) => {
    if (msg.type === 'state_update') {
      svStore.handleStateUpdate(msg as Record<string, unknown>)
    }
  })
})

onUnmounted(() => {
  disconnectWs?.()
})
</script>

<style scoped>
.demo-view-root {
  max-width: 1600px;
  margin: 0 auto;
  padding: 0.4rem 1rem 0.5rem;
  font-family: system-ui, sans-serif;
  height: calc(100vh - 1rem);
  display: flex;
  flex-direction: column;
}
.demo-top-row {
  margin-bottom: 0.5rem;
}
.demo-splitter {
  flex: 1;
  min-height: 0;
}
.demo-pane {
  overflow: hidden;
  height: 100%;
}
</style>
