<template>
  <Splitter layout="horizontal" class="log-splitter">

    <!-- ── Left panel: event list ──────────────────────────────────── -->
    <SplitterPanel :size="55" :min-size="20" class="log-left">
      <div class="log-header">
        <span
          class="log-title"
          v-tooltip.right="{
            value: 'Detailed run trace — tool calls, LLM steps, timing, and errors for each agent run',
            showDelay: 400
          }"
        >Event log</span>
        <button class="log-clear" @click="clearAll" title="Clear log">✕</button>
      </div>

      <div class="log-body" ref="logBodyEl">
        <div
          v-for="(line, i) in chatStore.eventLog"
          :key="i"
          :class="['log-line', { 'line-stats': line.isStats, 'is-selected': selectedLine === line }]"
          @click="selectedLine = line"
        >
          <span class="log-seq">{{ line.seq }}.</span>
          <span class="log-time">{{ line.time }}</span>
          <span :class="['log-tag', tagClass(line.tag)]">{{ line.tag }}</span>
          <span class="log-text">{{ line.text }}</span>
        </div>

        <div v-if="chatStore.eventLog.length === 0" class="log-empty">
          No events yet.
        </div>
      </div>
    </SplitterPanel>

    <!-- ── Right panel: event detail ──────────────────────────────── -->
    <SplitterPanel :size="45" :min-size="20" class="log-right">
      <EventDetailPanel :selected="selectedLine" />
    </SplitterPanel>

  </Splitter>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import Splitter from 'primevue/splitter'
import SplitterPanel from 'primevue/splitterpanel'
import { useChatStore } from '@/stores/chat'
import type { LogLine } from '@/stores/chat'
import EventDetailPanel from './EventDetailPanel.vue'

const chatStore  = useChatStore()
const logBodyEl  = ref<HTMLElement | null>(null)
const selectedLine = ref<LogLine | null>(null)

// Auto-scroll log list on new events
watch(
  () => chatStore.eventLog.length,
  () => nextTick(() => {
    requestAnimationFrame(() => {
      if (logBodyEl.value) {
        logBodyEl.value.scrollTop = logBodyEl.value.scrollHeight
      }
    })
  }),
)

// Clear selection when log is wiped
watch(
  () => chatStore.eventLog.length,
  (len) => { if (len === 0) selectedLine.value = null },
)

function clearAll() {
  chatStore.clearLog()
  selectedLine.value = null
}

function tagClass(tag: string): string {
  const map: Record<string, string> = {
    USER: 'tag-user', STEP: 'tag-step', TOOL: 'tag-tool', LLM: 'tag-llm',
    DONE: 'tag-done', ERR: 'tag-err', ERROR: 'tag-err', STAT: 'tag-stat',
    DEBUG: 'tag-debug', INFO: 'tag-info', WARNING: 'tag-warning',
  }
  return map[tag] ?? 'tag-other'
}
</script>

<style scoped>
/* ── Splitter fills the panel given by ChatView ────────────────────── */
.log-splitter {
  height: 100%;
  width: 100%;
}
/* Override PrimeVue Splitter default border / background */
:deep(.p-splitter) {
  border: none !important;
  background: transparent !important;
}
:deep(.p-splitter-gutter) {
  background: var(--p-content-border-color, #e2e8f0) !important;
  width: 4px !important;
}
:deep(.p-splitter-gutter:hover) {
  background: var(--p-primary-color, #1976d2) !important;
}

/* ── Left panel ────────────────────────────────────────────────────── */
.log-left {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.25rem 0.6rem;
  border-bottom: 1px solid var(--p-content-border-color, #e2e8f0);
  background: var(--p-surface-section, #f1f5f9);
  flex-shrink: 0;
}
.log-title {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--p-text-muted-color, #888);
  font-family: ui-monospace, "Cascadia Code", "Fira Code", monospace;
  cursor: default;
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
  font-family: ui-monospace, "Cascadia Code", "Fira Code", monospace;
  font-size: 0.78rem;
  background: var(--p-surface-ground, #f8fafc);
}
.log-line {
  display: flex;
  gap: 0.4rem;
  align-items: baseline;
  white-space: pre-wrap;
  word-break: break-word;
  border-radius: 3px;
  padding: 0.1rem 0.15rem;
  cursor: pointer;
}
.log-line:hover {
  background: var(--p-surface-hover, rgba(0, 0, 0, 0.04));
}
.log-line.is-selected {
  background: #dbeafe;
  outline: 1px solid #93c5fd;
}
.log-seq {
  color: var(--p-text-muted-color, #ccc);
  flex-shrink: 0;
  font-size: 0.68rem;
  min-width: 1.8rem;
  text-align: right;
  user-select: none;
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

/* Stats line — subtle highlight */
.line-stats {
  background: var(--p-surface-section, #f1f5f9);
  border-left: 3px solid #86efac;
  padding-left: 0.25rem !important;
}
.line-stats.is-selected {
  background: #dbeafe;
}

/* ── Right panel ───────────────────────────────────────────────────── */
.log-right {
  overflow: hidden;
  border-left: 1px solid var(--p-content-border-color, #e2e8f0);
}

/* ── Tag colour palette ────────────────────────────────────────────── */
.tag-user    { background: #dbeafe; color: #1e40af; }
.tag-step    { background: #e0e7ff; color: #3730a3; }
.tag-tool    { background: #fef3c7; color: #92400e; }
.tag-llm     { background: #ecfdf5; color: #065f46; }
.tag-stat    { background: #f0fdf4; color: #166534; }
.tag-done    { background: #dcfce7; color: #166534; }
.tag-err     { background: #fee2e2; color: #991b1b; }
.tag-debug   { background: #f1f5f9; color: #64748b; }
.tag-info    { background: #e0f2fe; color: #0369a1; }
.tag-warning { background: #fef9c3; color: #92400e; }
.tag-other   { background: #f3e8ff; color: #6b21a8; }
</style>
