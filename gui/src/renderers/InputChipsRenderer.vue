<template>
  <Fluid>
    <control-wrapper
      v-bind="controlWrapper"
      :styles="styles"
      :isFocused="isFocused"
      :appliedOptions="appliedOptions"
    >
      <div :class="styles.control.root + '-inner'">
        <label
          v-if="computedLabel"
          :for="control.id + '-input'"
          class="primevue-control-label"
        >
          {{ computedLabel }}
          <span v-if="control.required" class="primevue-control-required">*</span>
        </label>
        <div :class="['field-value', statusClass]">
          <InputChips
            :id="control.id + '-input'"
            :class="[styles.control.input, 'field-control', { 'p-invalid': control.errors }]"
            :disabled="!control.enabled"
            :placeholder="(appliedOptions as Record<string, unknown>).placeholder as string || 'Add item…'"
            :model-value="(control.data as string[]) || []"
            :separator="','"
            @update:model-value="onChange"
            @focus="handleFocus"
            @blur="onBlur"
          />
        </div>
        <small v-if="control.errors" class="primevue-control-error">{{ control.errors }}</small>
        <small
          v-else-if="control.description && persistentHint()"
          class="primevue-control-hint"
        >{{ control.description }}</small>
      </div>
    </control-wrapper>
  </Fluid>
</template>

<script lang="ts">
/**
 * Replacement for ChipsControlRenderer that uses PrimeVue v4 InputChips
 * instead of the deprecated Chips component.
 */
import {
  type ControlElement,
  type JsonFormsRendererRegistryEntry,
  rankWith,
  schemaMatches,
  uiTypeIs,
  and,
  type TesterContext,
  type JsonSchema,
  type UISchemaElement,
} from '@jsonforms/core'
import { rendererProps, useJsonFormsControl, type RendererProps } from '@jsonforms/vue'
import { computed, defineComponent } from 'vue'
import InputChips from 'primevue/inputchips'
import Fluid from 'primevue/fluid'
import {
  usePrimeVueControl,
  ControlWrapper,
} from '@chaoqing/jsonforms-vue-primevue'
import { useInspectorFieldAutosave } from '@/composables/useInspectorFieldAutosave'

const isArrayOfStrings = (schema: JsonSchema): boolean =>
  schema.type === 'array' &&
  schema.items !== undefined &&
  typeof schema.items === 'object' &&
  'type' in schema.items &&
  (schema.items as JsonSchema).type === 'string'

const isChipsControl = (
  uischema: UISchemaElement,
  schema: JsonSchema,
  context: TesterContext,
): boolean => {
  const chipsOption = (uischema as unknown as Record<string, unknown>)?.options !== undefined
    ? ((uischema as unknown as Record<string, unknown>).options as Record<string, unknown>)?.chips
    : undefined
  if (chipsOption === false) return false
  return schemaMatches(isArrayOfStrings)(uischema, schema, context)
}

const controlRenderer = defineComponent({
  name: 'input-chips-control-renderer',
  components: { ControlWrapper, InputChips, Fluid },
  props: { ...rendererProps<ControlElement>() },
  setup(props: RendererProps<ControlElement>) {
    const ctrl = usePrimeVueControl(
      useJsonFormsControl(props),
      (value: unknown) =>
        Array.isArray(value)
          ? (value as unknown[]).map((v) => String(v).trim()).filter((v) => v.length > 0)
          : [],
      300,
    )
    const autosave = useInspectorFieldAutosave(
      computed(() => ctrl.control.value.path),
    )
    function onChange(value: unknown) {
      autosave.markEditing()
      ctrl.onChange(value)
    }
    function onBlur() {
      ctrl.handleBlur()
      void autosave.onFieldBlur(ctrl.control.value.data)
    }
    return { ...ctrl, onChange, onBlur, statusClass: autosave.statusClass }
  },
})

export default controlRenderer

// Rank 6 > ChipsControlRenderer rank 5 — takes priority
export const inputChipsRendererEntry: JsonFormsRendererRegistryEntry = {
  renderer: controlRenderer,
  tester: rankWith(6, and(uiTypeIs('Control'), isChipsControl)),
}
</script>

<style scoped>
.control-inner {
  display: flex;
  flex-direction: column;
  gap: var(--p-spacing-1, 0.25rem);
}
.control-inner :deep(.p-inputchips) {
  width: 100%;
}
.primevue-control-label {
  font-weight: 500;
  color: var(--p-text-color);
  font-size: var(--p-font-size-sm, 0.875rem);
  display: flex;
  align-items: center;
  gap: var(--p-spacing-1, 0.25rem);
}
.primevue-control-required { color: var(--p-error-color, #f87171); font-weight: 600; }
.primevue-control-error {
  color: var(--p-error-color, #f87171);
  font-size: var(--p-font-size-sm, 0.875rem);
  display: block;
  margin-top: var(--p-spacing-1, 0.25rem);
}
.primevue-control-hint {
  color: var(--p-text-color-secondary, #6b7280);
  font-size: var(--p-font-size-sm, 0.875rem);
  display: block;
  margin-top: var(--p-spacing-1, 0.25rem);
}
</style>
