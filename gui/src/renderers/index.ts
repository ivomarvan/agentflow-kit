import type { JsonFormsRendererRegistryEntry, JsonSchema } from '@jsonforms/core'
import { and, rankWith, schemaMatches, uiTypeIs } from '@jsonforms/core'
import { primevueRenderers } from '@chaoqing/jsonforms-vue-primevue'
import { inputChipsRendererEntry } from './InputChipsRenderer.vue'
import { integerSliderRendererEntry } from './IntegerSliderRenderer.vue'
import { textareaRendererEntry } from './TextareaRenderer.vue'
import HorizontalFieldRenderer from './HorizontalFieldRenderer.vue'

const isTextareaField = (schema: JsonSchema): boolean =>
  schema.type === 'string' && (schema as Record<string, unknown>)['x-textarea'] === true

const hasIntegerRange = (schema: JsonSchema): boolean =>
  schema.type === 'integer' &&
  schema.minimum !== undefined &&
  schema.maximum !== undefined

/** Horizontal two-column layout for scalar controls (textarea and ranged integers excluded). */
const supportsHorizontalLayout = (schema: JsonSchema): boolean => {
  if (schema.type === 'array' || schema.type === 'object') return false
  if (isTextareaField(schema)) return false
  if (hasIntegerRange(schema)) return false
  if (schema.enum && schema.enum.length > 0) return true
  return ['string', 'number', 'integer', 'boolean'].includes(String(schema.type))
}

export const horizontalFieldRendererEntry: JsonFormsRendererRegistryEntry = {
  renderer: HorizontalFieldRenderer,
  tester: rankWith(5, and(uiTypeIs('Control'), schemaMatches(supportsHorizontalLayout))),
}

/** Inspector param editor — custom renderers first, then PrimeVue defaults. */
export const inspectorRenderers = Object.freeze([
  textareaRendererEntry,
  integerSliderRendererEntry,
  inputChipsRendererEntry,
  horizontalFieldRendererEntry,
  ...primevueRenderers,
])
