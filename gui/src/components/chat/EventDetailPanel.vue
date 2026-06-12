<template>
  <div class="detail-panel">
    <!-- Empty state -->
    <div v-if="!selected" class="detail-empty">
      <span class="detail-empty-icon">↑</span>
      <span>Select an event to see its details</span>
    </div>

    <!-- Event details -->
    <template v-else>
      <div class="detail-header">
        <span :class="['d-tag', tagClass(selected.tag)]">{{ selected.tag }}</span>
        <span class="d-title">{{ selected.text }}</span>
        <span class="d-meta">#{{ selected.seq }} · {{ selected.time }}</span>
      </div>
      <div class="detail-body">
        <div class="detail-tree" v-html="renderedHtml" />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { LogLine } from '@/stores/chat'

interface Props {
  selected: LogLine | null
}
const props = defineProps<Props>()

// ── Recursive JSON-aware renderer ─────────────────────────────────────

/** Try to parse a string as a JSON object or array; return null on failure. */
function tryParseJson(s: string): unknown {
  const t = s.trimStart()
  if (t[0] !== '{' && t[0] !== '[') return null
  try { return JSON.parse(s) } catch { return null }
}

/** Escape HTML special characters to prevent XSS in v-html. */
function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * Recursively render any JSON-safe value to an HTML string.
 * String values are auto-parsed as JSON when they start with { or [.
 */
function renderValue(val: unknown, depth = 0): string {
  if (val === null || val === undefined) {
    return `<span class="rv-null">null</span>`
  }
  if (typeof val === 'boolean') {
    return `<span class="rv-bool">${val}</span>`
  }
  if (typeof val === 'number') {
    return `<span class="rv-num">${val}</span>`
  }
  if (typeof val === 'string') {
    // Auto-parse embedded JSON strings
    const parsed = tryParseJson(val)
    if (parsed !== null && typeof parsed === 'object') {
      return (
        `<div class="rv-embedded">` +
        `<span class="rv-embedded-label">JSON ▾</span>` +
        renderValue(parsed, depth + 1) +
        `</div>`
      )
    }
    // Multi-line or long string → pre block
    if (val.length > 100 || val.includes('\n')) {
      return `<pre class="rv-str-long">${esc(val)}</pre>`
    }
    return `<span class="rv-str">${esc(val)}</span>`
  }
  if (Array.isArray(val)) {
    if (val.length === 0) return `<span class="rv-empty">[ ]</span>`
    const items = val.map((item, i) =>
      `<div class="rv-arr-item">` +
      `<span class="rv-idx">[${i}]</span>` +
      `<div class="rv-arr-val">${renderValue(item, depth + 1)}</div>` +
      `</div>`
    ).join('')
    return `<div class="rv-arr">${items}</div>`
  }
  if (typeof val === 'object') {
    const entries = Object.entries(val as Record<string, unknown>)
    if (entries.length === 0) return `<span class="rv-empty">{ }</span>`
    const rows = entries.map(([k, v]) =>
      `<div class="rv-row">` +
      `<span class="rv-key">${esc(k)}</span>` +
      `<div class="rv-val">${renderValue(v, depth + 1)}</div>` +
      `</div>`
    ).join('')
    // Top-level object: no extra indent; nested: add indent class
    return `<div class="${depth === 0 ? 'rv-obj-root' : 'rv-obj'}">${rows}</div>`
  }
  return `<span class="rv-other">${esc(String(val))}</span>`
}

// ── Structured renderer for ERROR/WARNING log events ──────────────────

/** Try to parse a Python repr-like string (single quotes, True/False/None) as JSON. */
function tryParsePythonLikeJson(s: string): unknown {
  try { return JSON.parse(s) } catch { /* fall through */ }
  try {
    return JSON.parse(
      s.replace(/'/g, '"')
        .replace(/\bTrue\b/g, 'true')
        .replace(/\bFalse\b/g, 'false')
        .replace(/\bNone\b/g, 'null'),
    )
  } catch { return null }
}

/**
 * Render a Python log message (possibly with a traceback) as structured HTML
 * with three collapsible sections: Summary, Python traceback, API error JSON.
 */
function renderErrorLog(message: string, logger?: string): string {
  const lines = message.split('\n')
  const tbIdx = lines.findIndex(l => l.startsWith('Traceback (most recent call last):'))

  // No traceback — render as plain pre block
  if (tbIdx === -1) {
    const src = logger ? `<span class="err-source">${esc(logger)}</span>` : ''
    return (
      `<div class="err-section">` +
      `<div class="err-section-label">Message ${src}</div>` +
      `<pre class="err-tb-code">${esc(message.trim())}</pre>` +
      `</div>`
    )
  }

  const summaryLines = lines.slice(0, tbIdx).filter(l => l.trim())
  const tbLines = lines.slice(tbIdx)
  const lastLine = tbLines[tbLines.length - 1] ?? ''

  // Try to extract API error JSON from the last exception line.
  // Pattern: "ExcType: Error code: NNN - [{...}]" or "ExcType: ... - {'key': ...}"
  let apiErrorHtml = ''
  const jsonMatch = lastLine.match(/- (\[?\{.+\}\]?)$/)
  if (jsonMatch) {
    const parsed = tryParsePythonLikeJson(jsonMatch[1])
    if (parsed !== null && typeof parsed === 'object') {
      apiErrorHtml = (
        `<div class="err-section err-api-section">` +
        `<div class="err-section-label">API error response</div>` +
        `<div class="err-api-body">${renderValue(parsed)}</div>` +
        `</div>`
      )
    }
  }

  // Remove the JSON part from the last traceback line for cleaner display
  const tbClean = jsonMatch
    ? [...tbLines.slice(0, -1), lastLine.slice(0, jsonMatch.index).trim()].join('\n')
    : tbLines.join('\n')

  const srcBadge = logger ? `<span class="err-source">${esc(logger)}</span>` : ''
  const summaryHtml = summaryLines.length
    ? (
      `<div class="err-section">` +
      `<div class="err-section-label">Summary ${srcBadge}</div>` +
      `<div class="err-summary-body">${summaryLines.map(l => `<div>${esc(l)}</div>`).join('')}</div>` +
      `</div>`
    )
    : ''

  const tbHtml = (
    `<div class="err-section">` +
    `<div class="err-section-label">Python traceback</div>` +
    `<pre class="err-tb-code">${esc(tbClean.trim())}</pre>` +
    `</div>`
  )

  return summaryHtml + tbHtml + apiErrorHtml
}

const renderedHtml = computed(() => {
  if (!props.selected?.detail) return '<span class="rv-null">(no detail)</span>'
  const detail = props.selected.detail as Record<string, unknown>
  // Specialised renderer for log events at ERROR/WARNING level
  if (
    detail.event_type === 'log' &&
    (detail.level === 'ERROR' || detail.level === 'WARNING') &&
    typeof detail.message === 'string'
  ) {
    return renderErrorLog(detail.message, detail.logger as string | undefined)
  }
  return renderValue(props.selected.detail)
})

// ── Tag CSS class (mirrors EventLogPanel) ─────────────────────────────
function tagClass(tag: string): string {
  const map: Record<string, string> = {
    USER: 'tag-user', STEP: 'tag-step', TOOL: 'tag-tool', LLM: 'tag-llm',
    DONE: 'tag-done', ERR: 'tag-err', ERROR: 'tag-err', STAT: 'tag-stat',
    DEBUG: 'tag-debug', INFO: 'tag-info', WARNING: 'tag-warning',
  }
  return map[tag] ?? 'tag-other'
}
</script>

<style scoped>
/* ── Panel layout ──────────────────────────────────────────────────── */
.detail-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  font-family: ui-monospace, "Cascadia Code", "Fira Code", monospace;
  font-size: 0.78rem;
  box-sizing: border-box;
  overflow: hidden;
}

/* ── Empty state ───────────────────────────────────────────────────── */
.detail-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 0.5rem;
  color: var(--p-text-muted-color, #94a3b8);
  font-size: 0.82rem;
  font-style: italic;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
}
.detail-empty-icon {
  font-size: 1.6rem;
  opacity: 0.35;
}

/* ── Event header ──────────────────────────────────────────────────── */
.detail-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.3rem 0.6rem;
  border-bottom: 1px solid var(--p-content-border-color, #e2e8f0);
  background: var(--p-surface-section, #f1f5f9);
  flex-shrink: 0;
}
.d-tag {
  flex-shrink: 0;
  font-weight: 700;
  font-size: 0.68rem;
  padding: 0.05rem 0.35rem;
  border-radius: 3px;
  text-transform: uppercase;
}
.d-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--p-text-color, #334155);
  font-size: 0.78rem;
}
.d-meta {
  flex-shrink: 0;
  color: var(--p-text-muted-color, #94a3b8);
  font-size: 0.72rem;
}

/* ── Scrollable body ───────────────────────────────────────────────── */
.detail-body {
  flex: 1;
  overflow: auto;   /* horizontal scroll when panel is too narrow */
  padding: 0.5rem 0.6rem;
}

/* ── Recursive value renderer ──────────────────────────────────────── */
.detail-tree {
  line-height: 1.6;
  min-width: 300px; /* ensures scrollbar appears before text becomes unreadable */
}
:deep(.rv-obj-root) {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
:deep(.rv-obj) {
  display: flex;
  flex-direction: column;
  gap: 0.1rem;
  border-left: 2px solid #e2e8f0;
  padding-left: 0.6rem;
  margin-left: 0.2rem;
}
:deep(.rv-row) {
  display: flex;
  gap: 0.4rem;
  align-items: flex-start;
}
:deep(.rv-key) {
  flex-shrink: 0;
  font-weight: 700;
  color: #1976d2;
  min-width: 6rem;
  max-width: 14rem;
  word-break: break-word;
}
:deep(.rv-val) {
  flex: 1;
  min-width: 15ch; /* value column: at least ~15 chars before horizontal scroll kicks in */
}
:deep(.rv-arr-val) {
  flex: 1;
  min-width: 15ch;
}
:deep(.rv-arr) {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  border-left: 2px solid #e2e8f0;
  padding-left: 0.6rem;
  margin-left: 0.2rem;
}
:deep(.rv-arr-item) {
  display: flex;
  gap: 0.4rem;
  align-items: flex-start;
}
:deep(.rv-idx) {
  flex-shrink: 0;
  color: #94a3b8;
  min-width: 2.2rem;
  text-align: right;
  font-size: 0.72rem;
}
:deep(.rv-str) {
  color: #059669;
  word-break: break-word;
}
:deep(.rv-str-long) {
  background: #f0fdf4;
  color: #065f46;
  padding: 6px 8px;
  border-radius: 4px;
  margin: 2px 0;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 0.78rem;
  line-height: 1.5;
  border-left: 3px solid #6ee7b7;
}
:deep(.rv-num)  { color: #d97706; }
:deep(.rv-bool) { color: #7c3aed; font-style: italic; }
:deep(.rv-null) { color: #94a3b8; font-style: italic; }
:deep(.rv-empty){ color: #94a3b8; }
:deep(.rv-other){ color: #64748b; }
:deep(.rv-embedded) {
  border-left: 3px solid #93c5fd;
  padding-left: 0.5rem;
  margin: 2px 0;
}
:deep(.rv-embedded-label) {
  font-size: 0.68rem;
  color: #3b82f6;
  font-weight: 600;
  display: block;
  margin-bottom: 2px;
}

/* ── Tag colours (shared with EventLogPanel) ───────────────────────── */
.tag-user    { background: #dbeafe; color: #1e40af; }
.tag-step    { background: #e0e7ff; color: #3730a3; }
.tag-tool    { background: #fef3c7; color: #92400e; }
.tag-llm     { background: #ecfdf5; color: #065f46; }
.tag-stat    { background: #f0fdf4; color: #166534; }
.tag-done    { background: #dcfce7; color: #166534; }
.tag-err     { background: #fee2e2; color: #991b1b; }
.tag-debug   { background: #f1f5f9; color: #64748b; }
.tag-info    { background: #e0f2fe; color: #0369a1; }
.tag-warning { background: #fef9c3; color: #92400e; }
.tag-other   { background: #f3e8ff; color: #6b21a8; }

/* ── Structured error log sections ────────────────────────────────── */
:deep(.err-section) {
  margin-bottom: 0.8rem;
}
:deep(.err-section-label) {
  font-size: 0.68rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
  margin-bottom: 0.25rem;
  display: flex;
  align-items: center;
  gap: 0.4rem;
}
:deep(.err-source) {
  font-weight: 400;
  font-style: italic;
  text-transform: none;
  color: #94a3b8;
}
:deep(.err-summary-body) {
  font-size: 0.82rem;
  color: #991b1b;
  font-weight: 500;
  background: #fff1f2;
  border-left: 3px solid #fca5a5;
  padding: 0.3rem 0.5rem;
  border-radius: 0 4px 4px 0;
}
:deep(.err-tb-code) {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 0.6rem 0.8rem;
  border-radius: 4px;
  font-size: 0.75rem;
  line-height: 1.55;
  overflow-x: auto;
  white-space: pre;
  word-break: normal;
  margin: 0;
}
:deep(.err-api-section) {
  margin-top: 0.4rem;
}
:deep(.err-api-body) {
  background: #fefce8;
  border-left: 3px solid #fde047;
  padding: 0.4rem 0.5rem;
  border-radius: 0 4px 4px 0;
}
</style>
