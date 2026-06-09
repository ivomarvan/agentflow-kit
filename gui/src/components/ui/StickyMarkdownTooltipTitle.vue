<template>
  <div class="sticky-title-wrap">
    <h1
      v-if="title"
      class="app-title"
      :class="{ 'has-doc': !!doc }"
      @mouseover="onTitleOver"
      @mousemove="onTitleMove"
      @mouseleave="onTargetMouseLeave"
    >
      {{ title }}
    </h1>
    <div
      v-show="visible"
      ref="panelEl"
      class="sticky-tooltip-panel"
      :class="{ sticky: frozen }"
      :style="panelStyle"
      @mouseenter="onPanelMouseEnter"
      @mouseleave="onPanelMouseLeave"
      v-html="renderedHtml"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef } from 'vue'
import { useStickyMarkdownTooltip } from '@/composables/useStickyMarkdownTooltip'

const props = defineProps<{
  /** Page title shown in the header. */
  title: string
  /** Markdown shown in the sticky tooltip on hover (empty = no tooltip). */
  doc: string
}>()

const doc = toRef(props, 'doc')
const {
  visible,
  frozen,
  panelStyle,
  renderedHtml,
  onTargetMouseOver,
  onTargetMouseMove,
  onTargetMouseLeave,
  onPanelMouseEnter,
  onPanelMouseLeave,
} = useStickyMarkdownTooltip(doc)
const panelEl = ref<HTMLElement | null>(null)

function panelWidth(): number {
  return panelEl.value?.offsetWidth ?? 420
}

function onTitleOver(e: MouseEvent) {
  onTargetMouseOver(e, panelWidth())
}

function onTitleMove(e: MouseEvent) {
  onTargetMouseMove(e, panelWidth())
}
</script>

<style scoped>
.sticky-title-wrap {
  position: relative;
}
.app-title {
  margin: 0;
  font-size: 1.5rem;
}
.app-title.has-doc {
  cursor: help;
}
.sticky-tooltip-panel {
  display: block;
  position: fixed;
  z-index: 1000;
  max-width: 400px;
  max-height: 72vh;
  overflow-y: auto;
  background: white;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 6px 28px rgba(0, 0, 0, 0.22);
  border-left: 4px solid #1976d2;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
  font-size: 13px;
  line-height: 1.6;
  pointer-events: none;
}
.sticky-tooltip-panel.sticky {
  pointer-events: auto;
}
.sticky-tooltip-panel :deep(h1),
.sticky-tooltip-panel :deep(h2),
.sticky-tooltip-panel :deep(h3) {
  font-weight: bold;
  margin: 0.5em 0 0.2em;
  color: #1976d2;
}
.sticky-tooltip-panel :deep(h1) {
  font-size: 1.05rem;
  border-bottom: 1px solid #eee;
  padding-bottom: 4px;
}
.sticky-tooltip-panel :deep(code) {
  background: #f0f4f8;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 0.88em;
}
.sticky-tooltip-panel :deep(pre) {
  background: #f0f4f8;
  padding: 8px;
  border-radius: 4px;
  margin: 6px 0;
  overflow-x: auto;
}
</style>
