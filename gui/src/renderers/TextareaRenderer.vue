<template>
  <div
    class="textarea-field-block"
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
    <div :class="['field-value', statusClass]">
      <Textarea
        :id="inputId"
        :model-value="(control.data as string) ?? ''"
        :disabled="!control.enabled"
        :invalid="!!control.errors"
        :auto-resize="true"
        :rows="4"
        class="field-control"
        @update:model-value="onChange"
        @blur="onBlur"
      />
      <small v-if="control.errors" class="field-error">{{ control.errors }}</small>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ControlElement } from '@jsonforms/core'
import { rendererProps, useJsonFormsControl } from '@jsonforms/vue'
import Textarea from 'primevue/textarea'
import { useInspectorFieldAutosave } from '@/composables/useInspectorFieldAutosave'

const props = defineProps(rendererProps<ControlElement>())
const { control, handleChange } = useJsonFormsControl(props)
const { statusClass, markEditing, onFieldBlur } = useInspectorFieldAutosave(
  computed(() => control.value.path),
)

const inputId = computed(() => `${control.value.id}-input`)
const computedLabel = computed(() => control.value.label ?? '')
const tooltipText = computed(() => control.value.description?.trim() || '')
const tooltipBinding = computed(() =>
  tooltipText.value
    ? { value: tooltipText.value, showDelay: 350 }
    : undefined,
)

function onChange(value: unknown) {
  markEditing()
  handleChange(control.value.path, value)
}

function onBlur() {
  void onFieldBlur(control.value.data)
}
</script>

<style scoped>
.textarea-field-block {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--p-content-border-color, #e8edf2);
}
.textarea-field-block:last-child {
  border-bottom: none;
}
.field-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--p-text-color, #334155);
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
  font-family: ui-monospace, monospace;
  font-size: 0.82rem;
  resize: vertical;
}
.field-error {
  display: block;
  margin-top: 0.2rem;
  font-size: 0.75rem;
  color: var(--p-red-500, #ef4444);
}
</style>
