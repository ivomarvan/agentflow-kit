<template>
  <div :class="['bubble', message.role]">
    <span :class="['bubble-tag', message.role === 'user' ? 'tag-user' : (message.isError ? 'tag-err' : 'tag-asst')]">
      {{ message.role === 'user' ? 'USER' : (message.isError ? 'ERR' : 'ASST') }}
    </span>
    <span :class="['bubble-text', { 'bubble-error': message.isError }]">
      <template v-if="message.role === 'user'">{{ message.content }}</template>
      <template v-else>
        <span v-if="message.isRunning" class="running-indicator">
          <i class="pi pi-spin pi-spinner" /> Running…
        </span>
        <template v-else>{{ message.result ?? 'Completed.' }}</template>
      </template>
    </span>
  </div>
</template>

<script setup lang="ts">
import type { ChatMessage } from '@/stores/chat'

defineProps<{ message: ChatMessage }>()
</script>

<style scoped>
.bubble {
  display: flex;
  gap: 0.45rem;
  align-items: baseline;
  padding: 0.1rem 0.15rem;
  border-radius: 3px;
  font-size: 0.86rem;
  line-height: 1.5;
}
.bubble:hover {
  background: var(--p-surface-hover, rgba(0, 0, 0, 0.04));
}

.bubble-tag {
  flex-shrink: 0;
  align-self: flex-start;
  font-weight: 700;
  font-size: 0.68rem;
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
  font-family: ui-monospace, 'Cascadia Code', monospace;
  margin-top: 0.15rem;
}
.tag-user { background: #dbeafe; color: #1e40af; }
.tag-asst { background: #e0e7ff; color: #3730a3; }
.tag-err  { background: #fee2e2; color: #991b1b; }

.bubble-text {
  flex: 1;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--p-text-color, #334155);
}
.bubble-error {
  color: #991b1b;
  background: #fff1f2;
  border-left: 3px solid #fca5a5;
  padding: 0.2rem 0.5rem;
  border-radius: 0 4px 4px 0;
  font-weight: 500;
}

.running-indicator {
  color: var(--p-text-muted-color, #888);
  font-style: italic;
}
</style>
