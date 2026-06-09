<template>
  <div class="event-log">
    <div class="log-header">
      <span class="log-title">Event log</span>
      <button class="log-clear" @click="chatStore.clearLog()" title="Clear log">✕</button>
    </div>
    <div class="log-body" ref="logBodyEl">
      <div
        v-for="(line, i) in chatStore.eventLog"
        :key="i"
        class="log-line"
      >
        <span class="log-time">{{ line.time }}</span>
        <span :class="['log-tag', tagClass(line.tag)]">{{ line.tag }}</span>
        <span class="log-text">{{ line.text }}</span>
      </div>
      <div v-if="chatStore.eventLog.length === 0" class="log-empty">
        No events yet.
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()
const logBodyEl = ref<HTMLElement | null>(null)

watch(
  () => chatStore.eventLog.length,
  () => nextTick(() => {
    if (logBodyEl.value) {
      logBodyEl.value.scrollTop = logBodyEl.value.scrollHeight
    }
  }),
)

function tagClass(tag: string): string {
  switch (tag) {
    case 'USER':    return 'tag-user'
    case 'STEP':    return 'tag-step'
    case 'DONE':    return 'tag-done'
    case 'ERR':     return 'tag-err'
    case 'DEBUG':   return 'tag-debug'
    case 'INFO':    return 'tag-info'
    case 'WARNING': return 'tag-warning'
    case 'ERROR':   return 'tag-err'
    default:        return 'tag-other'
  }
}
</script>

<style scoped>
.event-log {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--p-content-border-color, #e2e8f0);
  border-radius: 8px;
  background: var(--p-surface-ground, #f8fafc);
  font-family: ui-monospace, "Cascadia Code", "Fira Code", monospace;
  font-size: 0.78rem;
  height: 160px;
  flex-shrink: 0;
}
.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.25rem 0.6rem;
  border-bottom: 1px solid var(--p-content-border-color, #e2e8f0);
  background: var(--p-surface-section, #f1f5f9);
  border-radius: 8px 8px 0 0;
}
.log-title {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-text-muted-color, #888);
  font-family: inherit;
}
.log-clear {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--p-text-muted-color, #888);
  font-size: 0.75rem;
  padding: 0 0.2rem;
  line-height: 1;
  opacity: 0.6;
}
.log-clear:hover { opacity: 1; }

.log-body {
  flex: 1;
  overflow-y: auto;
  padding: 0.3rem 0.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
}
.log-line {
  display: flex;
  gap: 0.5rem;
  align-items: baseline;
  white-space: pre-wrap;
  word-break: break-word;
}
.log-time {
  color: var(--p-text-muted-color, #aaa);
  flex-shrink: 0;
  font-size: 0.72rem;
}
.log-tag {
  flex-shrink: 0;
  font-weight: 700;
  font-size: 0.68rem;
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.log-text {
  color: var(--p-text-color, #334155);
  flex: 1;
}
.log-empty {
  color: var(--p-text-muted-color, #aaa);
  font-style: italic;
  margin: auto;
  text-align: center;
}

/* tag colour palette */
.tag-user    { background: #dbeafe; color: #1e40af; }
.tag-step    { background: #e0e7ff; color: #3730a3; }
.tag-done    { background: #dcfce7; color: #166534; }
.tag-err     { background: #fee2e2; color: #991b1b; }
.tag-debug   { background: #f1f5f9; color: #64748b; }
.tag-info    { background: #e0f2fe; color: #0369a1; }
.tag-warning { background: #fef9c3; color: #92400e; }
.tag-other   { background: #f3e8ff; color: #6b21a8; }
</style>
