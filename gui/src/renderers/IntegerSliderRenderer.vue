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

    <div :class="['field-value', statusClass]">
      <div class="slider-row">
        <InputNumber
          :input-id="inputId"
          :model-value="numValue"
          :disabled="!control.enabled"
          :invalid="!!control.errors"
          :min="integerMin"
          :max="integerMax"
          :show-buttons="true"
          :use-grouping="false"
          input-class="slider-input"
          @update:model-value="onNumberChange"
          @blur="onBlur"
        />
        <Slider
          class="slider-track"
          :model-value="numValue ?? integerMin ?? 0"
          :min="integerMin ?? 0"
          :max="integerMax ?? 100"
          :step="1"
          :disabled="!control.enabled"
          @update:model-value="onSliderChange"
          @mouseup="onSliderRelease"
          @touchend="onSliderRelease"
        />
      </div>
      <small v-if="control.errors" class="field-error">{{ control.errors }}</small>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ControlElement, JsonSchema } from '@jsonforms/core'
import { rendererProps, useJsonFormsControl } from '@jsonforms/vue'
import InputNumber from 'primevue/inputnumber'
import Slider from 'primevue/slider'
import { useInspectorFieldAutosave } from '@/composables/useInspectorFieldAutosave'

const props = defineProps(rendererProps<ControlElement>())
const { control, handleChange } = useJsonFormsControl(props)
const { statusClass, markEditing, onFieldBlur } = useInspectorFieldAutosave(
  computed(() => control.value.path),
)

const resolvedSchema = computed(() => control.value.schema as JsonSchema)
const inputId = computed(() => `${control.value.id}-input`)
const computedLabel = computed(() => control.value.label ?? '')
const tooltipText = computed(() => control.value.description?.trim() || '')
const tooltipBinding = computed(() =>
  tooltipText.value
    ? { value: tooltipText.value, showDelay: 350 }
    : undefined,
)

const integerMin = computed(() => {
  const min = resolvedSchema.value.minimum
  return typeof min === 'number' ? min : undefined
})

const integerMax = computed(() => {
  const max = resolvedSchema.value.maximum
  return typeof max === 'number' ? max : undefined
})

const numValue = computed(() =>
  typeof control.value.data === 'number' ? control.value.data : null,
)

function onNumberChange(val: number | null) {
  markEditing()
  handleChange(control.value.path, val ?? integerMin.value ?? 0)
}

function onSliderChange(val: number | number[]) {
  markEditing()
  const next = Array.isArray(val) ? val[0] : val
  handleChange(control.value.path, next)
}

function onBlur() {
  void onFieldBlur(control.value.data)
}

function onSliderRelease() {
  void onFieldBlur(control.value.data)
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
.slider-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.slider-row :deep(.slider-input) {
  width: 5rem;
}
.slider-track {
  flex: 1;
}
.field-error {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.75rem;
  color: var(--p-red-500, #ef4444);
}
</style>
