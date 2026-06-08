<template>
  <Fluid>
    <control-wrapper
      v-bind="controlWrapper"
      :styles="styles"
      :isFocused="isFocused"
      :appliedOptions="appliedOptions"
    >
      <div
        class="control-inner"
        v-tooltip.top="tooltipBinding"
      >
        <label
          v-if="computedLabel"
          :for="control.id + '-input'"
          class="primevue-control-label"
        >
          {{ computedLabel }}
          <span v-if="control.required" class="primevue-control-required">*</span>
        </label>
        <div class="slider-row">
          <InputNumber
            :id="control.id + '-input'"
            :class="{ 'p-invalid': control.errors }"
            :disabled="!control.enabled"
            :model-value="numValue"
            :min="schema.minimum"
            :max="schema.maximum"
            :show-buttons="true"
            :use-grouping="false"
            input-class="slider-input"
            @update:model-value="onNumberChange"
            @focus="handleFocus"
            @blur="handleBlur"
          />
          <Slider
            v-if="hasRange"
            class="slider-track"
            :model-value="numValue ?? schema.minimum ?? 0"
            :min="schema.minimum ?? 0"
            :max="schema.maximum ?? 100"
            :step="1"
            :disabled="!control.enabled"
            @update:model-value="onSliderChange"
          />
        </div>
        <small v-if="control.errors" class="primevue-control-error">
          {{ control.errors }}
        </small>
      </div>
    </control-wrapper>
  </Fluid>
</template>

<script lang="ts">
import {
  type ControlElement,
  type JsonFormsRendererRegistryEntry,
  rankWith,
  type JsonSchema,
} from '@jsonforms/core'
import { rendererProps, useJsonFormsControl, type RendererProps } from '@jsonforms/vue'
import { computed, defineComponent } from 'vue'
import InputNumber from 'primevue/inputnumber'
import Slider from 'primevue/slider'
import Fluid from 'primevue/fluid'
import { usePrimeVueControl, ControlWrapper } from '@chaoqing/jsonforms-vue-primevue'

const hasMinMax = (schema: JsonSchema): boolean =>
  schema.type === 'integer' &&
  schema.minimum !== undefined &&
  schema.maximum !== undefined

const controlRenderer = defineComponent({
  name: 'integer-slider-control-renderer',
  components: { ControlWrapper, InputNumber, Slider, Fluid },
  props: { ...rendererProps<ControlElement>() },
  setup(props: RendererProps<ControlElement>) {
    const ctrl = usePrimeVueControl(
      useJsonFormsControl(props),
      (value: unknown) => (typeof value === 'number' ? value : null),
      0,
    )
    const schema = computed(() => ctrl.control.value.schema as JsonSchema)
    const hasRange = computed(
      () => schema.value.minimum !== undefined && schema.value.maximum !== undefined,
    )
    const numValue = computed(() =>
      typeof ctrl.control.value.data === 'number' ? ctrl.control.value.data : null,
    )
    const tooltipBinding = computed(() => {
      const text = ctrl.control.value.description?.trim()
      return text ? { value: text, showDelay: 350 } : undefined
    })
    function onNumberChange(val: number | null) {
      ctrl.onChange(val ?? schema.value.minimum ?? 0)
    }
    function onSliderChange(val: number | number[]) {
      const next = Array.isArray(val) ? val[0] : val
      ctrl.onChange(next)
    }
    return {
      ...ctrl,
      schema,
      hasRange,
      numValue,
      tooltipBinding,
      onNumberChange,
      onSliderChange,
    }
  },
})

export default controlRenderer

export const integerSliderRendererEntry: JsonFormsRendererRegistryEntry = {
  renderer: controlRenderer,
  tester: rankWith(10, (_ui, schema) => hasMinMax(schema)),
}
</script>

<style scoped>
.control-inner {
  display: flex;
  flex-direction: column;
  gap: var(--p-spacing-1, 0.25rem);
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
.primevue-control-label {
  font-weight: 500;
  color: var(--p-text-color);
  font-size: var(--p-font-size-sm, 0.875rem);
  display: flex;
  align-items: center;
  gap: 0.3rem;
}
.primevue-control-required { color: var(--p-error-color, #f87171); font-weight: 600; }
.primevue-control-error {
  color: var(--p-error-color, #f87171);
  font-size: var(--p-font-size-sm, 0.875rem);
}
</style>
