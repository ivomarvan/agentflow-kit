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

      <!-- Event log (collapsible) -->
      <div v-if="message.events.length" class="event-log">
        <button class="log-toggle" @click="logOpen = !logOpen">
          <i :class="logOpen ? 'pi pi-chevron-up' : 'pi pi-chevron-down'" />
          {{ message.events.length }} event{{ message.events.length !== 1 ? 's' : '' }}
        </button>
        <div v-if="logOpen" class="log-entries">
          <div v-for="(ev, i) in message.events" :key="i" class="log-entry">
            <component :is="getRenderer((ev.event_type ?? ev.type) as string)" :event="ev" />
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { ChatMessage } from '@/stores/chat'
import { getRenderer } from '@/event-renderers/index'

defineProps<{ message: ChatMessage }>()
const logOpen = ref(false)
</script>

<style scoped>
.bubble { max-width: 90%; }
.bubble.user { align-self: flex-end; }
.bubble-content {
  padding: 0.6rem 1rem;
  border-radius: 12px;
  line-height: 1.5;
}
.user-content {
  background: var(--p-primary-500, #6366f1);
  color: white;
  border-bottom-right-radius: 4px;
}
.assistant-content {
  background: var(--p-surface-100, #f1f5f9);
  border-bottom-left-radius: 4px;
}
.running-indicator {
  color: var(--p-text-muted-color, #888);
  font-style: italic;
}
.event-log { margin-top: 4px; }
.log-toggle {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.8rem;
  color: var(--p-text-muted-color, #888);
  padding: 2px 4px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.log-entries {
  margin-top: 4px;
  padding: 4px 8px;
  border-left: 2px solid var(--p-primary-200, #c7d2fe);
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 300px;
  overflow-y: auto;
}
.log-entry {
  font-size: 0.8rem;
  padding: 2px 0;
}
</style>
