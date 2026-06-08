<template>
  <div
    class="horizontal-field-row"
    v-tooltip.top="tooltipBinding"
  >
      <label
        v-if="computedLabel"
        :for="inputId"
        class="field-label"
      >
        {{ computedLabel }}
        <span v-if="control.required" class="field-required">*</span>
      </label>
      <span v-else class="field-label field-label--empty" />

      <div class="field-value">
        <Select
          v-if="fieldKind === 'enum'"
          :input-id="inputId"
          :model-value="(control.data as string) ?? ''"
          :options="enumOptions"
          :disabled="!control.enabled"
          :invalid="!!control.errors"
          class="field-control"
          @update:model-value="onChange"
        />
        <div v-else-if="fieldKind === 'boolean'" class="field-control field-control--checkbox">
          <Checkbox
            :input-id="inputId"
            :model-value="!!control.data"
            :disabled="!control.enabled"
            :invalid="!!control.errors"
            binary
            @update:model-value="onChange"
          />
        </div>
        <InputNumber
          v-else-if="fieldKind === 'integer'"
          :input-id="inputId"
          :model-value="control.data as number | null"
          :disabled="!control.enabled"
          :invalid="!!control.errors"
          :use-grouping="false"
          :min="integerMin"
          :max="integerMax"
          class="field-control"
          @update:model-value="onChange"
        />
        <InputNumber
          v-else-if="fieldKind === 'number'"
          :input-id="inputId"
          :model-value="control.data as number | null"
          :disabled="!control.enabled"
          :invalid="!!control.errors"
          :min-fraction-digits="0"
          :max-fraction-digits="6"
          :use-grouping="false"
          class="field-control"
          @update:model-value="onChange"
        />
        <InputText
          v-else
          :id="inputId"
          :model-value="(control.data as string) ?? ''"
          :disabled="!control.enabled"
          :invalid="!!control.errors"
          class="field-control"
          @update:model-value="onChange"
        />
        <small v-if="control.errors" class="field-error">{{ control.errors }}</small>
      </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ControlElement, JsonSchema } from '@jsonforms/core'
import { rendererProps, useJsonFormsControl } from '@jsonforms/vue'
import InputText from 'primevue/inputtext'
import InputNumber from 'primevue/inputnumber'
import Checkbox from 'primevue/checkbox'
import Select from 'primevue/select'

const props = defineProps(rendererProps<ControlElement>())
const { control, handleChange } = useJsonFormsControl(props)

const inputId = computed(() => `${control.value.id}-input`)
const computedLabel = computed(() => control.value.label ?? '')
const tooltipText = computed(() => control.value.description?.trim() || '')
const tooltipBinding = computed(() =>
  tooltipText.value
    ? { value: tooltipText.value, showDelay: 350 }
    : undefined,
)

const resolvedSchema = computed(() => control.value.schema as JsonSchema)

const fieldKind = computed((): 'enum' | 'boolean' | 'integer' | 'number' | 'string' => {
  const schema = resolvedSchema.value
  if (schema.enum && schema.enum.length > 0) return 'enum'
  if (schema.type === 'boolean') return 'boolean'
  if (schema.type === 'integer') return 'integer'
  if (schema.type === 'number') return 'number'
  return 'string'
})

const enumOptions = computed(() => (resolvedSchema.value.enum ?? []) as string[])

const integerMin = computed(() => {
  const min = resolvedSchema.value.minimum
  return typeof min === 'number' ? min : undefined
})

const integerMax = computed(() => {
  const max = resolvedSchema.value.maximum
  return typeof max === 'number' ? max : undefined
})

function onChange(value: unknown) {
  handleChange(control.value.path, value)
}
</script>

<style scoped>
.horizontal-field-row {
  display: grid;
  grid-template-columns: minmax(7rem, 38%) 1fr;
  gap: 0.5rem 0.75rem;
  align-items: center;
  padding: 0.35rem 0;
  border-bottom: 1px solid var(--p-content-border-color, #e8edf2);
}
.horizontal-field-row:last-child {
  border-bottom: none;
}
.field-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--p-text-color, #334155);
  word-break: break-word;
}
.field-label--empty {
  visibility: hidden;
}
.field-required {
  color: var(--p-red-500, #ef4444);
  margin-left: 0.15rem;
}
.field-value {
  min-width: 0;
}
.field-control {
  width: 100%;
}
.field-control--checkbox {
  display: flex;
  align-items: center;
  min-height: 2.25rem;
}
.field-error {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.75rem;
  color: var(--p-red-500, #ef4444);
}
</style>
