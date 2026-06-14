<template>
  <div class="fw-field">
    <label class="fw-label" :for="inputId">{{ label }}</label>
    <Select
      v-if="isSelect"
      :inputId="inputId"
      :modelValue="modelValue"
      :options="enumOptions"
      optionLabel="label"
      optionValue="value"
      class="fw-control"
      @update:modelValue="emit('update:modelValue', $event)"
    />
    <DatePicker
      v-else-if="isDate"
      :inputId="inputId"
      :modelValue="dateValue"
      dateFormat="yy-mm-dd"
      class="fw-control"
      @update:modelValue="onDateChange"
    />
    <InputNumber
      v-else-if="isNumber"
      :inputId="inputId"
      :modelValue="numberValue"
      :min="schema.minimum"
      :max="schema.maximum"
      :useGrouping="false"
      :minFractionDigits="isInteger ? 0 : undefined"
      :maxFractionDigits="isInteger ? 0 : 2"
      class="fw-control"
      @update:modelValue="emit('update:modelValue', $event)"
    />
    <ToggleButton
      v-else-if="isBoolean"
      :modelValue="Boolean(modelValue)"
      onLabel="On"
      offLabel="Off"
      class="fw-control"
      @update:modelValue="emit('update:modelValue', $event)"
    />
    <InputText
      v-else
      :id="inputId"
      :modelValue="String(modelValue ?? '')"
      class="fw-control"
      @update:modelValue="emit('update:modelValue', $event)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { InputText, InputNumber, DatePicker, ToggleButton, Select } from 'primevue'
import type { JsonSchemaField } from '@/services/api'

interface Props {
  name: string
  schema: JsonSchemaField
  modelValue: unknown
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()

const inputId = computed(() => `field-${props.name}`)
const label = computed(() => props.schema.description ?? props.name)

const widget = computed(() => props.schema['x-widget'] ?? '')
const isSelect = computed(() => widget.value === 'select' || (props.schema.enum?.length ?? 0) > 0)
const isDate = computed(() => widget.value === 'date')
const isBoolean = computed(() => props.schema.type === 'boolean')
const isInteger = computed(() => props.schema.type === 'integer')
const isNumber = computed(() =>
  widget.value === 'number' || props.schema.type === 'integer' || props.schema.type === 'number',
)

const enumOptions = computed(() =>
  (props.schema.enum ?? []).map(v => ({ label: String(v), value: v })),
)

const numberValue = computed(() =>
  typeof props.modelValue === 'number' ? props.modelValue : undefined,
)

const dateValue = computed(() => {
  if (!props.modelValue) return null
  const parsed = new Date(String(props.modelValue))
  return Number.isNaN(parsed.getTime()) ? null : parsed
})

function onDateChange(value: Date | Date[] | (Date | null)[] | null | undefined) {
  if (!value || Array.isArray(value)) {
    emit('update:modelValue', '')
    return
  }
  // Use local date components to avoid UTC timezone shift (toISOString() converts to UTC,
  // which shifts the date one day back for timezones east of UTC+0).
  const y = value.getFullYear()
  const m = String(value.getMonth() + 1).padStart(2, '0')
  const d = String(value.getDate()).padStart(2, '0')
  emit('update:modelValue', `${y}-${m}-${d}`)
}
</script>

<style scoped>
.fw-field {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 0.6rem;
}
.fw-label {
  font-size: 0.8rem;
  color: var(--p-text-muted-color, #64748b);
}
.fw-control {
  width: 100%;
}
</style>
