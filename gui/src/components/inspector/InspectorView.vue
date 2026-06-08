<template>
  <Splitter class="inspector-splitter">
    <SplitterPanel :size="45" :minSize="20" class="inspector-pane inspector-pane--graph">
      <StructureView />
    </SplitterPanel>
    <SplitterPanel :size="55" :minSize="25" class="inspector-pane inspector-pane--params">
      <SettingsView />
    </SplitterPanel>
  </Splitter>
</template>

<script setup lang="ts">
import { Splitter, SplitterPanel } from 'primevue'
import StructureView from '@/components/structure/StructureView.vue'
import SettingsView from '@/components/settings/SettingsView.vue'
</script>

<style scoped>
.inspector-splitter {
  height: calc(100vh - 130px);
  min-height: 480px;
}
.inspector-pane {
  overflow: auto;
}
.inspector-pane--graph {
  padding: 0;
}
.inspector-pane--params {
  padding: 0 0.5rem;
}
</style>
