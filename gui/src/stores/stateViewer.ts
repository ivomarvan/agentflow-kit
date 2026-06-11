/**
 * Pinia store for the live state viewer.
 *
 * Receives StateUpdateEvent payloads from the WebSocket stream and maintains
 * the current display schema + state data for StateViewerPanel.vue.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export interface FieldDisplay {
  type: 'icon'
  icon: string
  on_color: string
  off_color: string
  unit: string
}

export interface FieldSchema {
  title?: string
  description?: string
  type: 'float' | 'int' | 'bool' | 'str' | 'object' | 'list' | 'unknown'
  display?: FieldDisplay
  room_hint?: { label: string; col_span: number }
  panel_hint?: { label: string; layout: string }
  nested_schema?: Record<string, FieldSchema>
}

export const useStateViewerStore = defineStore('stateViewer', () => {
  /** Display schema — sent once per run from the backend. */
  const schema = ref<Record<string, FieldSchema> | null>(null)
  /** Current state data — updated after every tool call. */
  const stateData = ref<Record<string, unknown> | null>(null)

  const hasData = computed(() => schema.value !== null && stateData.value !== null)

  function handleStateUpdate(event: Record<string, unknown>) {
    if (event.display_schema) {
      schema.value = event.display_schema as Record<string, FieldSchema>
    }
    if (event.state_data) {
      stateData.value = event.state_data as Record<string, unknown>
    }
  }

  function clear() {
    schema.value = null
    stateData.value = null
  }

  return { schema, stateData, hasData, handleStateUpdate, clear }
})
