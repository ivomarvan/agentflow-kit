import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Shared selection state between StructureView (graph) and SettingsView (params).
 *
 * ``selectedNode`` is the single source of truth for linked highlight in both
 * panes. It persists until the user selects another node or param group.
 */
export const useStructureStore = defineStore('structure', () => {
  /** ID of the linked selection (graph node key / top-level config group key). */
  const selectedNode = ref<string | null>(null)
  /** Interactive graph HTML from ``GET /api/graph`` (same as ``graph --browser``). */
  const graphHtml = ref<string | null>(null)

  /**
   * Select a graph node or param group; both Inspector panes stay in sync.
   * @param nodeId - Graphviz node title (maps to top-level config key when present).
   */
  function selectNode(nodeId: string) {
    selectedNode.value = nodeId
  }

  /** Clear linked selection in both panes. */
  function clearSelection() {
    selectedNode.value = null
  }

  /**
   * Cache the interactive graph HTML page.
   * @param html - Full HTML document from the API.
   */
  function setGraphHtml(html: string) {
    graphHtml.value = html
  }

  return { selectedNode, graphHtml, selectNode, clearSelection, setGraphHtml }
})
