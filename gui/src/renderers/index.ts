import type { JsonFormsRendererRegistryEntry, JsonSchema } from '@jsonforms/core'
import { and, rankWith, schemaMatches, uiTypeIs } from '@jsonforms/core'
import { vanillaRenderers } from '@jsonforms/vue-vanilla'
import HorizontalFieldRenderer from './HorizontalFieldRenderer.vue'

/** Scalar controls except textarea (handled in T105-05). */
const supportsHorizontalLayout = (schema: JsonSchema): boolean => {
  if (schema.type === 'array' || schema.type === 'object') return false
  if (schema.type === 'string' && schema.format === 'textarea') return false
  if (schema.enum && schema.enum.length > 0) return true
  return ['string', 'number', 'integer', 'boolean'].includes(String(schema.type))
}

export const horizontalFieldRendererEntry: JsonFormsRendererRegistryEntry = {
  renderer: HorizontalFieldRenderer,
  tester: rankWith(5, and(uiTypeIs('Control'), schemaMatches(supportsHorizontalLayout))),
}

/** Inspector param editor renderers — prepend custom entries before vanilla fallbacks. */
export const inspectorRenderers = Object.freeze([
  horizontalFieldRendererEntry,
  ...vanillaRenderers,
])
