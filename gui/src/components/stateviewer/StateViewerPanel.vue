<template>
  <div v-if="svStore.hasData" class="state-viewer">
    <div class="sv-header">
      <span
        class="sv-title"
        v-tooltip.right="{
          value: 'Real-time agent state — fields highlighted in amber changed in the last update',
          showDelay: 400
        }"
      >Live State</span>
    </div>
    <div
      class="sv-grid"
      :style="{ gridTemplateColumns: `repeat(${totalCols}, minmax(0, 1fr))` }"
    >
      <!-- Room boxes (nested models with room_hint) -->
      <div
        v-for="(fieldSchema, fieldName) in rooms"
        :key="fieldName"
        class="sv-room"
        :style="{ gridColumn: `span ${fieldSchema.room_hint?.col_span ?? 1}` }"
      >
        <div class="room-label">{{ fieldSchema.room_hint?.label ?? fieldName }}</div>
        <div class="room-fields">
          <div
            v-for="(subSchema, subName) in fieldSchema.nested_schema"
            :key="subName"
            :class="['room-field', { changed: isChanged(String(fieldName), String(subName)) }]"
            v-tooltip.top="{ value: fieldTooltip(String(fieldName), String(subName), subSchema), showDelay: 350 }"
          >
            <template v-if="subSchema.display?.type === 'icon'">
              <!-- Boolean icon field -->
              <template v-if="subSchema.type === 'bool'">
                <span class="field-emoji">{{ iconEmoji(subSchema.display.icon) }}</span>
                <span
                  class="field-bool-dot"
                  :style="{
                    background: getRoomValue(String(fieldName), String(subName))
                      ? subSchema.display.on_color
                      : subSchema.display.off_color
                  }"
                />
              </template>
              <!-- Numeric / string icon field -->
              <template v-else>
                <span class="field-emoji">{{ iconEmoji(subSchema.display.icon) }}</span>
                <span class="field-value">
                  {{ formatNum(getRoomValue(String(fieldName), String(subName)), subSchema) }}
                </span>
              </template>
            </template>
            <!-- Fallback: title + value -->
            <template v-else>
              <span class="field-label">{{ subSchema.title ?? subName }}</span>
              <span class="field-value">{{ getRoomValue(String(fieldName), String(subName)) }}</span>
            </template>
          </div>
        </div>
      </div>

      <!-- Flat scalar fields (not rooms) -->
      <div v-if="flatFields.length > 0" class="sv-room sv-flat">
        <div class="room-label">State</div>
        <div class="room-fields">
          <div
            v-for="[fName, fSchema] in flatFields"
            :key="fName"
            :class="['room-field', { changed: isChanged('', fName) }]"
            v-tooltip.top="{ value: `${fSchema.title ?? fName}: ${svStore.stateData?.[fName]}`, showDelay: 350 }"
          >
            <span v-if="fSchema.display?.icon" class="field-emoji">
              {{ iconEmoji(fSchema.display.icon) }}
            </span>
            <span class="field-label">{{ fSchema.title ?? fName }}</span>
            <span class="field-value">{{ svStore.stateData?.[fName] }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, watch, ref } from 'vue'
import { useStateViewerStore } from '@/stores/stateViewer'
import type { FieldSchema } from '@/stores/stateViewer'

const svStore = useStateViewerStore()

// ---------------------------------------------------------------------------
// Emoji mapping for icon names
// ---------------------------------------------------------------------------
const ICON_EMOJI: Record<string, string> = {
  bulb: '💡', thermometer: '🌡️', flame: '🔥', person: '👤',
  snowflake: '❄️', lock: '🔒', door: '🚪', tv: '📺',
  bell: '🔔', wifi: '📶', plug: '🔌', fan: '💨',
  sun: '☀️', moon: '🌙', water: '💧', car: '🚗',
  clock: '🕐', star: '⭐', check: '✅', calendar: '📅',
  power: '⚡', bed: '🛏️', sofa: '🛋️', tree: '🌳',
}

function iconEmoji(name?: string): string {
  return name ? (ICON_EMOJI[name] ?? '●') : '●'
}

// ---------------------------------------------------------------------------
// Schema-derived computed properties
// ---------------------------------------------------------------------------

/** All fields with room_hint — rendered as room boxes. */
const rooms = computed(() => {
  if (!svStore.schema) return {} as Record<string, FieldSchema>
  return Object.fromEntries(
    Object.entries(svStore.schema).filter(([, f]) => !!f.room_hint && f.type === 'object')
  )
})

/** Scalar / non-room fields — rendered in a flat box. */
const flatFields = computed((): [string, FieldSchema][] => {
  if (!svStore.schema) return []
  return Object.entries(svStore.schema).filter(([, f]) => !f.room_hint || f.type !== 'object')
})

/** Total grid column count (sum of col_spans). */
const totalCols = computed(() => {
  const sum = Object.values(rooms.value).reduce(
    (acc, f) => acc + (f.room_hint?.col_span ?? 1),
    0,
  )
  return Math.max(sum, flatFields.value.length > 0 ? sum + 1 : sum, 1)
})

// ---------------------------------------------------------------------------
// Data helpers
// ---------------------------------------------------------------------------

function getRoomValue(fieldName: string, subName: string): unknown {
  if (!svStore.stateData) return undefined
  const roomData = svStore.stateData[fieldName] as Record<string, unknown> | undefined
  return roomData?.[subName]
}

function fieldTooltip(fieldName: string, subName: string, schema: FieldSchema): string {
  const title = schema.title ?? subName
  const value = getRoomValue(fieldName, subName)
  if (value === undefined || value === null) return title
  if (schema.type === 'bool') {
    return `${title}: ${value ? 'ON' : 'OFF'}`
  }
  if (schema.type === 'float' || schema.type === 'int') {
    const unit = schema.display?.unit ?? ''
    return `${title}: ${value}${unit}`
  }
  return `${title}: ${String(value)}`
}

function formatNum(value: unknown, schema: FieldSchema): string {
  if (value === null || value === undefined) return '—'
  const num = typeof value === 'number' ? value : Number(value)
  const formatted = Number.isInteger(num) ? String(num) : num.toFixed(1)
  return formatted + (schema.display?.unit ?? '')
}

// ---------------------------------------------------------------------------
// Change detection for flash animation
// ---------------------------------------------------------------------------

/** Previously seen stateData — used to compute changed fields. */
const prevData = ref<Record<string, unknown> | null>(null)
/** Set of "fieldName/subName" keys that changed in the last update. */
const changedKeys = ref<Set<string>>(new Set())

watch(
  () => svStore.stateData,
  (next, prev) => {
    if (!next) { changedKeys.value = new Set(); return }
    const changed = new Set<string>()
    for (const [roomKey, roomVal] of Object.entries(next)) {
      const prevRoom = (prev as Record<string, unknown> | null)?.[roomKey]
      if (typeof roomVal === 'object' && roomVal !== null) {
        for (const [subKey, subVal] of Object.entries(roomVal as Record<string, unknown>)) {
          const prevSub = (prevRoom as Record<string, unknown> | undefined)?.[subKey]
          if (prevSub !== subVal) changed.add(`${roomKey}/${subKey}`)
        }
      } else {
        const prevFlat = (prev as Record<string, unknown> | null)?.[roomKey]
        if (prevFlat !== roomVal) changed.add(`/${roomKey}`)
      }
    }
    changedKeys.value = changed
    prevData.value = prev as Record<string, unknown>
    // Clear flash after 1.5 s
    setTimeout(() => { changedKeys.value = new Set() }, 1500)
  },
  { deep: true },
)

function isChanged(fieldName: string, subName: string): boolean {
  return changedKeys.value.has(fieldName ? `${fieldName}/${subName}` : `/${subName}`)
}
</script>

<style scoped>
.state-viewer {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--p-content-border-color, #e2e8f0);
  border-radius: 8px;
  background: var(--p-surface-ground, #f8fafc);
  flex-shrink: 0;
  overflow: hidden;
}
.sv-header {
  display: flex;
  align-items: center;
  padding: 0.22rem 0.6rem;
  border-bottom: 1px solid var(--p-content-border-color, #e2e8f0);
  background: var(--p-surface-section, #f1f5f9);
}
.sv-title {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--p-text-muted-color, #888);
  cursor: default;
}
.sv-grid {
  display: grid;
  gap: 0.4rem;
  padding: 0.4rem 0.5rem;
  align-items: start;
}
.sv-room {
  border: 1px solid var(--p-content-border-color, #e2e8f0);
  border-radius: 6px;
  padding: 0.3rem 0.4rem;
  background: var(--p-surface-card, #fff);
  min-width: 0;
}
.sv-flat {
  background: var(--p-surface-ground, #f8fafc);
}
.room-label {
  font-size: 0.62rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--p-text-muted-color, #94a3b8);
  margin-bottom: 0.3rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.room-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  align-items: flex-start;
}
.room-field {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.08rem;
  padding: 0.15rem 0.25rem;
  border-radius: 5px;
  min-width: 32px;
  /* Flash animation: changed → amber background, then fade back */
  transition: background-color 1.5s ease-out;
}
.room-field.changed {
  background-color: rgba(251, 191, 36, 0.35) !important;
  transition: none;
}
.field-emoji {
  font-size: 1.05rem;
  line-height: 1;
}
.field-bool-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1.5px solid rgba(0, 0, 0, 0.08);
  transition: background-color 0.3s ease;
  flex-shrink: 0;
}
.field-value {
  font-size: 0.74rem;
  font-weight: 700;
  font-family: ui-monospace, "Cascadia Code", monospace;
  color: var(--p-text-color, #1e293b);
  white-space: nowrap;
  text-align: center;
}
.field-label {
  font-size: 0.6rem;
  color: var(--p-text-muted-color, #94a3b8);
  text-align: center;
  white-space: nowrap;
}
</style>
