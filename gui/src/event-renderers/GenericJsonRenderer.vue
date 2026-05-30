<template>
  <div class="json-event">
    <span class="event-type">{{ event.event_type ?? event.type }}</span>
    <pre class="json-body">{{ formatted }}</pre>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WsMessage } from '@/services/wsClient'

const props = defineProps<{ event: WsMessage }>()
const formatted = computed(() => JSON.stringify(props.event, null, 2))
</script>

<style scoped>
.json-event { font-size: 0.8rem; }
.event-type {
  display: inline-block;
  background: var(--p-primary-100, #e0e7ff);
  color: var(--p-primary-700, #3730a3);
  border-radius: 4px;
  padding: 0 6px;
  font-size: 0.75rem;
  font-weight: 600;
  margin-bottom: 4px;
}
.json-body {
  margin: 0;
  font-family: monospace;
  font-size: 0.75rem;
  color: var(--p-text-muted-color, #555);
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
