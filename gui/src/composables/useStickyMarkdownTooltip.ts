import { marked } from 'marked'
import { ref, type Ref } from 'vue'
import {
  TOOLTIP_HIDE_MS,
  TOOLTIP_OFFSET_X,
  TOOLTIP_OFFSET_Y,
} from '@/constants/stickyTooltip'

/**
 * Interactive follow-cursor Markdown tooltip.
 *
 * The panel always has pointer-events enabled so the user can scroll or click
 * links at any time.  A grace period (TOOLTIP_HIDE_MS) between leaving the
 * hover target and the panel hiding lets the cursor move from the target into
 * the panel without the panel disappearing.
 *
 * @param markdown - Reactive Markdown source; empty string hides the tooltip.
 */
export function useStickyMarkdownTooltip(markdown: Ref<string>) {
  const visible = ref(false)
  const panelStyle = ref({ left: '0px', top: '0px' })
  const renderedHtml = ref('')

  let hideTimer: ReturnType<typeof setTimeout> | null = null
  let ttSource: string | null = null

  function clearHide() {
    if (hideTimer) {
      clearTimeout(hideTimer)
      hideTimer = null
    }
  }

  function hideTip() {
    clearHide()
    visible.value = false
    ttSource = null
  }

  function scheduleHide() {
    clearHide()
    hideTimer = setTimeout(hideTip, TOOLTIP_HIDE_MS)
  }

  function placeTip(clientX: number, clientY: number, panelWidth: number) {
    const x = clientX + TOOLTIP_OFFSET_X
    const y = clientY + TOOLTIP_OFFSET_Y
    const w = panelWidth || 420
    const left =
      x + w > window.innerWidth ? clientX - w - 4 : x
    panelStyle.value = {
      left: `${Math.max(0, left)}px`,
      top: `${Math.max(8, y)}px`,
    }
  }

  function showTip(md: string, source: string, e: MouseEvent, panelWidth: number) {
    if (!md) {
      hideTip()
      return
    }
    if (ttSource !== source) {
      ttSource = source
      renderedHtml.value = marked.parse(md) as string
      visible.value = true
      placeTip(e.clientX, e.clientY, panelWidth)
    }
    clearHide()
  }

  function onTargetMouseOver(e: MouseEvent, panelWidth: number) {
    const md = markdown.value
    if (!md) return
    showTip(md, 'title', e, panelWidth)
  }

  function onTargetMouseMove(e: MouseEvent, panelWidth: number) {
    if (!visible.value) return
    placeTip(e.clientX, e.clientY, panelWidth)
  }

  function onTargetMouseLeave() {
    scheduleHide()
  }

  function onPanelMouseEnter() {
    clearHide()
  }

  function onPanelMouseLeave() {
    scheduleHide()
  }

  return {
    visible,
    panelStyle,
    renderedHtml,
    onTargetMouseOver,
    onTargetMouseMove,
    onTargetMouseLeave,
    onPanelMouseEnter,
    onPanelMouseLeave,
  }
}
