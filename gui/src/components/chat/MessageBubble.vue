<template>
  <div :class="['bubble', message.role]">
    <!-- User bubble -->
    <template v-if="message.role === 'user'">
      <div class="bubble-content user-content">{{ message.content }}</div>
    </template>

    <!-- Assistant bubble -->
    <template v-else>
      <div class="bubble-content assistant-content">
        <span v-if="message.isRunning" class="running-indicator">
          <i class="pi pi-spin pi-spinner" /> Running…
        </span>
        <span v-else class="result-text">{{ message.result ?? 'Completed.' }}</span>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import type { ChatMessage } from '@/stores/chat'

defineProps<{ message: ChatMessage }>()
</script>

<style scoped>
.bubble {
  width: 100%;
  box-sizing: border-box;
}
.bubble-content {
  padding: 0.45rem 0.9rem;
  border-radius: 8px;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.user-content {
  background: var(--p-primary-500, #6366f1);
  color: white;
  border-bottom-left-radius: 4px;
}
.assistant-content {
  background: var(--p-surface-100, #f1f5f9);
  border-bottom-right-radius: 4px;
}
.running-indicator {
  color: var(--p-text-muted-color, #888);
  font-style: italic;
}
</style>
