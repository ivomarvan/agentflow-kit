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
          { highlighted: structureStore.selectedNode === propKey },
        ]"
        @click="onGroupClick(propKey)"
      >
        <h3 class="group-title">{{ propKey }}</h3>
        <ParamGroupForm
          :group-key="propKey"
          :data="(draftValues[propKey] as Record<string, unknown>) ?? {}"
          :schema="(propSchema as JsonSchema)"
          :renderers="renderers"
          @change="(e: CoreActions) => onGroupChange(propKey, (e as { data: unknown }).data)"
        />
      </div>
    </div>

    <div v-else class="empty-state">
      No configurable parameters found.
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick, provide } from 'vue'
import type { CoreActions } from '@jsonforms/core'
import type { JsonSchema } from '@jsonforms/core'
import { api } from '@/services/api'
import { useStructureStore } from '@/stores/structure'
import { inspectorRenderers } from '@/renderers'
import ParamGroupForm from './ParamGroupForm.vue'
import {
  INSPECTOR_AUTOSAVE_KEY,
  type FieldStatus,
  type InspectorFieldAutosaveContext,
} from '@/composables/useInspectorFieldAutosave'

const renderers = inspectorRenderers

const loading = ref(true)
const configSchema = ref<Record<string, unknown> | null>(null)
const configValues = ref<Record<string, unknown>>({})
const draftValues = ref<Record<string, unknown>>({})
const fieldStatus = ref<Record<string, FieldStatus>>({})

const structureStore = useStructureStore()

const topLevelProperties = computed<Record<string, unknown>>(() => {
  const schema = configSchema.value
  if (!schema || typeof schema !== 'object') return {}
  return (schema as Record<string, Record<string, unknown>>).properties ?? {}
})

function fieldStatusKey(groupKey: string, fieldKey: string): string {
  return `${groupKey}.${fieldKey}`
}

function initFieldStatus(config: Record<string, unknown>): void {
  const status: Record<string, FieldStatus> = {}
  for (const [groupKey, groupData] of Object.entries(config)) {
    if (groupData === null || typeof groupData !== 'object' || Array.isArray(groupData)) continue
    for (const fieldKey of Object.keys(groupData as Record<string, unknown>)) {
      status[fieldStatusKey(groupKey, fieldKey)] = 'saved'
    }
  }
  fieldStatus.value = status
}

const autosaveContext: InspectorFieldAutosaveContext = {
  markEditing(groupKey: string, fieldKey: string) {
    fieldStatus.value[fieldStatusKey(groupKey, fieldKey)] = 'editing'
  },
  statusClass(groupKey: string, fieldKey: string) {
    return `field-value--${fieldStatus.value[fieldStatusKey(groupKey, fieldKey)] ?? 'saved'}`
  },
  saveField,
}

provide(INSPECTOR_AUTOSAVE_KEY, autosaveContext)

onMounted(async () => {
  try {
    const [schema, config] = await Promise.all([api.getSchema(), api.getConfig()])
    configSchema.value = schema
    configValues.value = config
    draftValues.value = JSON.parse(JSON.stringify(config)) as Record<string, unknown>
    initFieldStatus(config)
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
  const params = cloneForPostMessage(data)
  if (!params) return
  graphIframe()?.contentWindow?.postMessage(
    { type: 'af:updateTooltip', nodeId: groupKey, params },
    '*',
  )
}

async function saveField(groupKey: string, fieldKey: string, value: unknown): Promise<void> {
  const statusKey = fieldStatusKey(groupKey, fieldKey)
  if (fieldStatus.value[statusKey] !== 'editing') return

  try {
    await api.setConfig(`${groupKey}.${fieldKey}`, value)

    const groupDraft = {
      ...(draftValues.value[groupKey] as Record<string, unknown>),
      [fieldKey]: value,
    }
    draftValues.value = { ...draftValues.value, [groupKey]: groupDraft }

    const groupConfig = {
      ...(configValues.value[groupKey] as Record<string, unknown>),
      [fieldKey]: JSON.parse(JSON.stringify(value)) as unknown,
    }
    configValues.value = { ...configValues.value, [groupKey]: groupConfig }

    fieldStatus.value[statusKey] = 'saved'

    const params = cloneForPostMessage(groupDraft)
    if (params) {
      graphIframe()?.contentWindow?.postMessage(
        { type: 'af:updateTooltip', nodeId: groupKey, params },
        '*',
      )
    }
  } catch (e) {
    console.error('Failed to save field', groupKey, fieldKey, e)
    fieldStatus.value[statusKey] = 'error'
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

/* Per-field save status — border only on the value control */
.param-group :deep(.field-value--saved .field-control),
.param-group :deep(.field-value--saved textarea),
.param-group :deep(.field-value--saved .p-inputtext),
.param-group :deep(.field-value--saved .p-select),
.param-group :deep(.field-value--saved .p-inputnumber),
.param-group :deep(.field-value--saved .p-inputchips),
.param-group :deep(.field-value--saved .slider-row .p-inputnumber),
.param-group :deep(.field-value--saved .slider-row .p-slider) {
  box-shadow: none;
}

.param-group :deep(.field-value--editing .field-control),
.param-group :deep(.field-value--editing textarea),
.param-group :deep(.field-value--editing .p-inputtext),
.param-group :deep(.field-value--editing .p-select),
.param-group :deep(.field-value--editing .p-inputnumber),
.param-group :deep(.field-value--editing .p-inputchips),
.param-group :deep(.field-value--editing .slider-row .p-inputnumber),
.param-group :deep(.field-value--editing .slider-row .p-slider) {
  outline: 2px solid #f59e0b;
  outline-offset: 1px;
  border-radius: 4px;
}

.param-group :deep(.field-value--error .field-control),
.param-group :deep(.field-value--error textarea),
.param-group :deep(.field-value--error .p-inputtext),
.param-group :deep(.field-value--error .p-select),
.param-group :deep(.field-value--error .p-inputnumber),
.param-group :deep(.field-value--error .p-inputchips),
.param-group :deep(.field-value--error .slider-row .p-inputnumber),
.param-group :deep(.field-value--error .slider-row .p-slider) {
  outline: 2px solid #ef4444;
  outline-offset: 1px;
  border-radius: 4px;
}
</style>
