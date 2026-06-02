import { marked } from 'marked'
import { ref, type Ref } from 'vue'
import {
  TOOLTIP_HIDE_MS,
  TOOLTIP_IDLE_MS,
  TOOLTIP_OFFSET_X,
  TOOLTIP_OFFSET_Y,
} from '@/constants/stickyTooltip'

/**
 * Follow-cursor Markdown tooltip that freezes after cursor idle (graph HTML parity).
 *
 * @param markdown - Reactive Markdown source; empty string hides the tooltip.
 */
export function useStickyMarkdownTooltip(markdown: Ref<string>) {
  const visible = ref(false)
  const frozen = ref(false)
  const panelStyle = ref({ left: '0px', top: '0px' })
  const renderedHtml = ref('')

  let hideTimer: ReturnType<typeof setTimeout> | null = null
  let idleTimer: ReturnType<typeof setTimeout> | null = null
  let ttSource: string | null = null

  function clearHide() {
    if (hideTimer) {
      clearTimeout(hideTimer)
      hideTimer = null
    }
  }

  function clearIdle() {
    if (idleTimer) {
      clearTimeout(idleTimer)
      idleTimer = null
    }
  }

  function hideTip() {
    clearHide()
    clearIdle()
    visible.value = false
    frozen.value = false
    ttSource = null
  }

  function scheduleHide() {
    clearHide()
    hideTimer = setTimeout(hideTip, TOOLTIP_HIDE_MS)
  }

  function freezeTip() {
    frozen.value = true
  }

  function armIdle() {
    clearIdle()
    idleTimer = setTimeout(freezeTip, TOOLTIP_IDLE_MS)
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
      frozen.value = false
      visible.value = true
      placeTip(e.clientX, e.clientY, panelWidth)
    }
    clearHide()
    if (!frozen.value) armIdle()
  }

  function onTargetMouseOver(e: MouseEvent, panelWidth: number) {
    const md = markdown.value
    if (!md) return
    showTip(md, 'title', e, panelWidth)
  }

  function onTargetMouseMove(e: MouseEvent, panelWidth: number) {
    if (!visible.value || frozen.value) return
    placeTip(e.clientX, e.clientY, panelWidth)
    armIdle()
  }

  function onTargetMouseLeave() {
    scheduleHide()
  }

  function onPanelMouseEnter() {
    clearHide()
    freezeTip()
  }

  function onPanelMouseLeave() {
    hideTip()
  }

  return {
    visible,
    frozen,
    panelStyle,
    renderedHtml,
    onTargetMouseOver,
    onTargetMouseMove,
    onTargetMouseLeave,
    onPanelMouseEnter,
    onPanelMouseLeave,
  }
}
