<template>
  <JsonForms
    :data="data"
    :schema="schema"
    :renderers="renderers"
    @change="(e: CoreActions) => emit('change', e)"
  />
</template>

<script setup lang="ts">
import { provide } from 'vue'
import { JsonForms } from '@jsonforms/vue'
import type { CoreActions, JsonSchema, JsonFormsRendererRegistryEntry } from '@jsonforms/core'
import { PARAM_GROUP_KEY } from '@/composables/useInspectorFieldAutosave'

const props = defineProps<{
  groupKey: string
  data: Record<string, unknown>
  schema: JsonSchema
  renderers: readonly JsonFormsRendererRegistryEntry[]
}>()

const emit = defineEmits<{
  change: [event: CoreActions]
}>()

provide(PARAM_GROUP_KEY, props.groupKey)
</script>
