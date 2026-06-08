<template>
  <div class="settings-view">
    <div v-if="loading" class="loading">
      <i class="pi pi-spin pi-spinner" /> Loading configuration…
    </div>

    <div v-else-if="configSchema && configValues" class="schema-form">
      <div
        v-for="(propSchema, propKey) in topLevelProperties"
        :key="propKey"
        :id="`param-group-${propKey}`"
        :class="[
          'param-group',
          statusClass(propKey),
          { highlighted: structureStore.selectedNode === propKey },
        ]"
        @click="onGroupClick(propKey)"
      >
        <h3 class="group-title">{{ propKey }}</h3>
        <div
          @focusin="onGroupFocus(propKey)"
          @focusout="onGroupBlur(propKey)"
        >
          <JsonForms
            :data="(draftValues[propKey] as Record<string, unknown>) ?? {}"
            :schema="(propSchema as JsonSchema)"
            :renderers="renderers"
            @change="(e: CoreActions) => onGroupChange(propKey, (e as { data: unknown }).data)"
          />
        </div>
      </div>
    </div>

    <div v-else class="empty-state">
      No configurable parameters found.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { JsonForms } from '@jsonforms/vue'
import type { CoreActions } from '@jsonforms/core'
import type { JsonSchema } from '@jsonforms/core'
import { api } from '@/services/api'
import { useStructureStore } from '@/stores/structure'
import { inspectorRenderers } from '@/renderers'

type GroupStatus = 'saved' | 'editing' | 'error'

const renderers = inspectorRenderers

const loading = ref(true)
const configSchema = ref<Record<string, unknown> | null>(null)
const configValues = ref<Record<string, unknown>>({})
const draftValues = ref<Record<string, unknown>>({})
const groupStatus = ref<Record<string, GroupStatus>>({})

const blurTimers: Record<string, ReturnType<typeof setTimeout>> = {}

const structureStore = useStructureStore()

const topLevelProperties = computed<Record<string, unknown>>(() => {
  const schema = configSchema.value
  if (!schema || typeof schema !== 'object') return {}
  return (schema as Record<string, Record<string, unknown>>).properties ?? {}
})

function statusClass(propKey: string): string {
  return `param-group--${groupStatus.value[propKey] ?? 'saved'}`
}

onMounted(async () => {
  try {
    const [schema, config] = await Promise.all([api.getSchema(), api.getConfig()])
    configSchema.value = schema
    configValues.value = config
    draftValues.value = JSON.parse(JSON.stringify(config)) as Record<string, unknown>
    for (const key of Object.keys(config)) {
      groupStatus.value[key] = 'saved'
    }
  } catch (e) {
    console.error('Failed to load config', e)
  } finally {
    loading.value = false
  }
})

watch(() => structureStore.selectedNode, async (nodeId) => {
  if (!nodeId) return
  await nextTick()
  const el = document.getElementById(`param-group-${nodeId}`)
  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
})

function onGroupClick(propKey: string) {
  structureStore.selectNode(propKey)
}

function graphIframe(): HTMLIFrameElement | null {
  return document.querySelector('iframe.graph-frame')
}

function cloneForPostMessage(data: unknown): Record<string, unknown> | null {
  if (data === null || typeof data !== 'object' || Array.isArray(data)) return null
  try {
    return JSON.parse(JSON.stringify(data)) as Record<string, unknown>
  } catch {
    return null
  }
}

function onGroupChange(groupKey: string, data: unknown) {
  draftValues.value = { ...draftValues.value, [groupKey]: data }
  groupStatus.value[groupKey] = 'editing'
  const params = cloneForPostMessage(data)
  if (!params) return
  graphIframe()?.contentWindow?.postMessage(
    { type: 'af:updateTooltip', nodeId: groupKey, params },
    '*',
  )
}

function onGroupFocus(groupKey: string) {
  clearTimeout(blurTimers[groupKey])
}

function onGroupBlur(groupKey: string) {
  blurTimers[groupKey] = setTimeout(() => {
    void saveGroup(groupKey)
  }, 150)
}

async function saveGroup(groupKey: string) {
  if (groupStatus.value[groupKey] !== 'editing') return
  try {
    const groupData = draftValues.value[groupKey] as Record<string, unknown> | undefined
    if (!groupData) return
    for (const [paramKey, value] of Object.entries(groupData)) {
      await api.setConfig(`${groupKey}.${paramKey}`, value)
    }
    configValues.value = {
      ...configValues.value,
      [groupKey]: JSON.parse(JSON.stringify(groupData)) as unknown,
    }
    groupStatus.value[groupKey] = 'saved'
  } catch (e) {
    console.error('Failed to save', groupKey, e)
    groupStatus.value[groupKey] = 'error'
  }
}
</script>

<style scoped>
.settings-view { padding: 1rem; }
.loading { padding: 2rem; text-align: center; }
.empty-state { padding: 2rem; text-align: center; color: var(--p-text-muted-color, #aaa); }
.param-group {
  margin-bottom: 1rem;
  padding: 0.75rem 1rem;
  border: 2px solid var(--p-content-border-color, #e2e8f0);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.25s, background 0.25s;
}
.param-group--saved {
  border-color: var(--p-content-border-color, #e2e8f0);
}
.param-group--editing {
  border-color: #f59e0b;
  background: #fffbeb;
}
.param-group--error {
  border-color: #ef4444;
  background: #fff5f5;
}
.param-group.highlighted {
  background: #fefce8;
  border-color: #facc15;
}
.group-title {
  margin: 0 0 0.75rem 0;
  font-size: 0.95rem;
  font-weight: 600;
  text-transform: capitalize;
  color: var(--p-primary-600, #4f46e5);
}
.param-group :deep(.control-description),
.param-group :deep(.primevue-control-hint) {
  display: none;
}
</style>
