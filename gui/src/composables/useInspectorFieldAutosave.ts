import { computed, inject, type ComputedRef, type Ref } from 'vue'

export type FieldStatus = 'saved' | 'editing' | 'error'

export const PARAM_GROUP_KEY = Symbol('paramGroupKey')

export interface InspectorFieldAutosaveContext {
  markEditing: (groupKey: string, fieldKey: string) => void
  saveField: (groupKey: string, fieldKey: string, value: unknown) => Promise<void>
  statusClass: (groupKey: string, fieldKey: string) => string
}

export const INSPECTOR_AUTOSAVE_KEY = Symbol('inspectorAutosave')

/** Extract leaf property name from a JsonForms control path. */
export function extractFieldKey(path: string): string {
  const parts = path.replace(/^#/, '').split('/').filter(Boolean)
  const propsIdx = parts.indexOf('properties')
  if (propsIdx >= 0 && parts[propsIdx + 1]) {
    return parts[propsIdx + 1]
  }
  return parts[parts.length - 1] ?? path
}

const NO_OP_CONTEXT: InspectorFieldAutosaveContext = {
  markEditing: () => {},
  saveField: async () => {},
  statusClass: () => 'field-value--saved',
}

/**
 * Per-field autosave hooks for JsonForms renderers inside the inspector panel.
 *
 * @param controlPath - Reactive JsonForms control path.
 * @returns Status class and handlers to call on change and blur.
 */
export function useInspectorFieldAutosave(
  controlPath: Ref<string> | ComputedRef<string>,
) {
  const groupKey = inject<string>(PARAM_GROUP_KEY, '')
  const ctx = inject<InspectorFieldAutosaveContext>(INSPECTOR_AUTOSAVE_KEY, NO_OP_CONTEXT)

  const fieldKey = computed(() => extractFieldKey(controlPath.value))

  const statusClass = computed(() =>
    groupKey ? ctx.statusClass(groupKey, fieldKey.value) : 'field-value--saved',
  )

  function markEditing(): void {
    if (groupKey) {
      ctx.markEditing(groupKey, fieldKey.value)
    }
  }

  async function onFieldBlur(value: unknown): Promise<void> {
    if (groupKey) {
      await ctx.saveField(groupKey, fieldKey.value, value)
    }
  }

  return { statusClass, markEditing, onFieldBlur, fieldKey }
}
