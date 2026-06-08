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
        <Textarea
          :id="control.id + '-input'"
          :class="[styles.control.input, { 'p-invalid': control.errors }]"
          :disabled="!control.enabled"
          :model-value="(control.data as string) ?? ''"
          :auto-resize="true"
          :rows="4"
          @update:model-value="onChange"
          @focus="handleFocus"
          @blur="handleBlur"
        />
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
import Textarea from 'primevue/textarea'
import Fluid from 'primevue/fluid'
import { usePrimeVueControl, ControlWrapper } from '@chaoqing/jsonforms-vue-primevue'

const isTextareaString = (schema: JsonSchema): boolean =>
  schema.type === 'string' && (schema as Record<string, unknown>)['x-textarea'] === true

const controlRenderer = defineComponent({
  name: 'textarea-control-renderer',
  components: { ControlWrapper, Textarea, Fluid },
  props: { ...rendererProps<ControlElement>() },
  setup(props: RendererProps<ControlElement>) {
    const ctrl = usePrimeVueControl(
      useJsonFormsControl(props),
      (value: unknown) => (typeof value === 'string' ? value : ''),
      300,
    )
    const tooltipBinding = computed(() => {
      const text = ctrl.control.value.description?.trim()
      return text ? { value: text, showDelay: 350 } : undefined
    })
    return { ...ctrl, tooltipBinding }
  },
})

export default controlRenderer

export const textareaRendererEntry: JsonFormsRendererRegistryEntry = {
  renderer: controlRenderer,
  tester: rankWith(10, (_ui, schema) => isTextareaString(schema)),
}
</script>

<style scoped>
.control-inner {
  display: flex;
  flex-direction: column;
  gap: var(--p-spacing-1, 0.25rem);
}
.control-inner :deep(textarea) {
  width: 100%;
  font-family: ui-monospace, monospace;
  font-size: 0.82rem;
  resize: vertical;
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
