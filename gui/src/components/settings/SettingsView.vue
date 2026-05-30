<template>
  <div class="settings-view">
    <div class="settings-toolbar">
      <Button
        label="Apply Changes"
        icon="pi pi-check"
        :disabled="!hasChanges"
        @click="applyChanges"
      />
      <Button
        label="Reset"
        icon="pi pi-refresh"
        severity="secondary"
        :disabled="!hasChanges"
        @click="resetChanges"
      />
      <span v-if="saveStatus" class="save-status">{{ saveStatus }}</span>
    </div>

    <div v-if="loading" class="loading">
      <i class="pi pi-spin pi-spinner" /> Loading configuration…
    </div>

    <div v-else-if="configSchema && configValues" class="schema-form">
      <div
        v-for="(propSchema, propKey) in topLevelProperties"
        :key="propKey"
        :id="`param-group-${propKey}`"
        :class="['param-group', { highlighted: highlightedGroup === propKey }]"
      >
        <h3 class="group-title">{{ propKey }}</h3>
        <JsonForms
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
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { JsonForms } from '@jsonforms/vue'
import type { CoreActions } from '@jsonforms/core'
import type { JsonSchema } from '@jsonforms/core'
import { vanillaRenderers } from '@jsonforms/vue-vanilla'
import { Button } from 'primevue'
import { api } from '@/services/api'
import { useStructureStore } from '@/stores/structure'

const renderers = Object.freeze([...vanillaRenderers])

const loading = ref(true)
const configSchema = ref<Record<string, unknown> | null>(null)
const configValues = ref<Record<string, unknown>>({})
const draftValues = ref<Record<string, unknown>>({})
const hasChanges = ref(false)
const saveStatus = ref('')
const highlightedGroup = ref<string | null>(null)

const structureStore = useStructureStore()

const topLevelProperties = computed<Record<string, unknown>>(() => {
  const schema = configSchema.value
  if (!schema || typeof schema !== 'object') return {}
  return (schema as Record<string, Record<string, unknown>>).properties ?? {}
})

onMounted(async () => {
  try {
    const [schema, config] = await Promise.all([api.getSchema(), api.getConfig()])
    configSchema.value = schema
    configValues.value = config
    draftValues.value = JSON.parse(JSON.stringify(config)) as Record<string, unknown>
  } catch (e) {
    console.error('Failed to load config', e)
  } finally {
    loading.value = false
  }
})

// Scroll to highlighted group when a structure node is selected
watch(() => structureStore.selectedNode, async (nodeId) => {
  if (!nodeId) return
  await nextTick()
  const el = document.getElementById(`param-group-${nodeId}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
    highlightedGroup.value = nodeId
    setTimeout(() => { highlightedGroup.value = null }, 2000)
  }
})

function onGroupChange(groupKey: string, data: unknown) {
  draftValues.value = { ...draftValues.value, [groupKey]: data }
  hasChanges.value = true
}

async function applyChanges() {
  saveStatus.value = 'Saving…'
  try {
    for (const [groupKey, groupData] of Object.entries(draftValues.value)) {
      if (typeof groupData === 'object' && groupData !== null) {
        for (const [paramKey, value] of Object.entries(groupData as Record<string, unknown>)) {
          await api.setConfig(`${groupKey}.${paramKey}`, value)
        }
      }
    }
    configValues.value = JSON.parse(JSON.stringify(draftValues.value)) as Record<string, unknown>
    hasChanges.value = false
    saveStatus.value = '✓ Saved'
    setTimeout(() => { saveStatus.value = '' }, 2000)
  } catch (e) {
    saveStatus.value = '✗ Error saving'
    console.error(e)
  }
}

function resetChanges() {
  draftValues.value = JSON.parse(JSON.stringify(configValues.value)) as Record<string, unknown>
  hasChanges.value = false
  saveStatus.value = ''
}
</script>

<style scoped>
.settings-view { padding: 1rem; }
.settings-toolbar {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  margin-bottom: 1.5rem;
}
.save-status { font-size: 0.85rem; color: var(--p-text-muted-color, #666); }
.loading { padding: 2rem; text-align: center; }
.empty-state { padding: 2rem; text-align: center; color: var(--p-text-muted-color, #aaa); }
.param-group {
  margin-bottom: 1.5rem;
  padding: 1rem;
  border: 1px solid var(--p-content-border-color, #e2e8f0);
  border-radius: 8px;
  transition: background 0.4s;
}
.param-group.highlighted {
  background: var(--p-yellow-50, #fefce8);
  border-color: var(--p-yellow-400, #facc15);
}
.group-title {
  margin: 0 0 0.75rem 0;
  font-size: 0.95rem;
  font-weight: 600;
  text-transform: capitalize;
  color: var(--p-primary-600, #4f46e5);
}
</style>
