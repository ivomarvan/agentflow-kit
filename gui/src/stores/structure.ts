import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Shared state between StructureView and SettingsView.
 *
 * When the user selects a graph node (future), `selectedNode` can drive
 * Settings scroll/highlight.
 */
export const useStructureStore = defineStore('structure', () => {
  /** ID of the currently selected graph node (matches a top-level config key). */
  const selectedNode = ref<string | null>(null)
  /** Interactive graph HTML from ``GET /api/graph`` (same as ``graph --browser``). */
  const graphHtml = ref<string | null>(null)

  /**
   * Mark a graph node as selected, triggering Settings scroll/highlight.
   * @param nodeId - Graphviz node title (maps to top-level config key).
   */
  function selectNode(nodeId: string) {
    selectedNode.value = nodeId
  }

  /**
   * Cache the interactive graph HTML page.
   * @param html - Full HTML document from the API.
   */
  function setGraphHtml(html: string) {
    graphHtml.value = html
  }

  return { selectedNode, graphHtml, selectNode, setGraphHtml }
})
