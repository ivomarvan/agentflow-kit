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
  /** True when the agent app has a live_state model (set on GUI mount via /api/live-state). */
  const hasLiveStateCapability = ref(false)

  const hasData = computed(() => schema.value !== null && stateData.value !== null)

  /** Initialise from the /api/live-state response (called once on mount). */
  function initFromApi(displaySchema: Record<string, FieldSchema>, initialData: Record<string, unknown>) {
    hasLiveStateCapability.value = true
    schema.value = displaySchema
    stateData.value = initialData
  }

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
    // hasLiveStateCapability intentionally kept — the app still has live_state
  }

  return { schema, stateData, hasData, hasLiveStateCapability, initFromApi, handleStateUpdate, clear }
})
