/**
 * Pinia store for LiveModel demo mode (ActionPanel).
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api, type DemoToolSchema } from '@/services/api'
import { useStateViewerStore, type FieldSchema } from '@/stores/stateViewer'

export const useDemoStore = defineStore('demo', () => {
  const tools = ref<DemoToolSchema[]>([])
  const lastResult = ref<string | null>(null)
  const lastError = ref<string | null>(null)
  const isLoading = ref(false)

  async function loadTools(): Promise<void> {
    tools.value = await api.getDemoTools()
  }

  async function loadLiveState(): Promise<void> {
    const info = await api.getLiveState()
    if (info.has_live_state && info.display_schema && info.state_data) {
      useStateViewerStore().initFromApi(
        info.display_schema as Record<string, FieldSchema>,
        info.state_data,
      )
    }
  }

  async function callAction(toolName: string, params: Record<string, unknown>): Promise<void> {
    isLoading.value = true
    lastResult.value = null
    lastError.value = null
    try {
      const response = await api.callDemoAction(toolName, params)
      if (response.error) {
        lastError.value = response.error
      } else {
        lastResult.value = response.result
      }
    } catch (err) {
      lastError.value = err instanceof Error ? err.message : String(err)
    } finally {
      isLoading.value = false
    }
  }

  return { tools, lastResult, lastError, isLoading, loadTools, loadLiveState, callAction }
})
