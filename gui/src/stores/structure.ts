import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Shared state between StructureView and SettingsView.
 *
 * When the user clicks a graph node in StructureView, `selectedNode` is set
 * here so that SettingsView can react (scroll + highlight).
 */
export const useStructureStore = defineStore('structure', () => {
  /** ID of the currently selected graph node (matches a top-level config key). */
  const selectedNode = ref<string | null>(null)
  /** Raw SVG string fetched from /api/graph — cached to avoid re-fetching. */
  const svgContent = ref<string | null>(null)

  /**
   * Mark a graph node as selected, triggering Settings scroll/highlight.
   * @param nodeId - Graphviz node title (maps to top-level config key).
   */
  function selectNode(nodeId: string) {
    selectedNode.value = nodeId
  }

  /**
   * Cache the SVG graph content.
   * @param svg - Raw SVG markup string from the API.
   */
  function setSvg(svg: string) {
    svgContent.value = svg
  }

  return { selectedNode, svgContent, selectNode, setSvg }
})
