<template>
  <div class="af-card">
    <button type="button" class="af-header" @click="expanded = !expanded">
      <i :class="expanded ? 'pi pi-chevron-down' : 'pi pi-chevron-right'" />
      <span class="af-name">{{ tool.name }}</span>
    </button>
    <p v-if="tool.description" class="af-desc">{{ tool.description }}</p>

    <div v-if="expanded" class="af-body">
      <FieldWidget
        v-for="(fieldSchema, fieldName) in fields"
        :key="fieldName"
        :name="String(fieldName)"
        :schema="fieldSchema"
        v-model="formValues[fieldName]"
      />
      <div class="af-actions">
        <Button
          label="Execute"
          icon="pi pi-play"
          size="small"
          :disabled="!canSubmit || submitting"
          :loading="submitting"
          @click="submit"
        />
      </div>
      <p v-if="result" class="af-result">{{ result }}</p>
      <p v-if="error" class="af-error">{{ error }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Button } from 'primevue'
import FieldWidget from '@/components/demo/FieldWidget.vue'
import { api, type DemoToolSchema } from '@/services/api'

interface Props {
  tool: DemoToolSchema
}

const props = defineProps<Props>()
const emit = defineEmits<{ actionResult: [payload: { tool: string; result: string | null; error: string | null }] }>()

const expanded = ref(false)
const submitting = ref(false)
const result = ref<string | null>(null)
const error = ref<string | null>(null)

const fields = computed(() => props.tool.parameters.properties ?? {})
const required = computed(() => new Set(props.tool.parameters.required ?? []))

const formValues = reactive<Record<string, unknown>>({})

for (const [name, schema] of Object.entries(props.tool.parameters.properties ?? {})) {
  if (schema.default !== undefined) {
    formValues[name] = schema.default
  } else if (schema.type === 'boolean') {
    formValues[name] = false
  } else if (schema.type === 'integer' || schema.type === 'number') {
    formValues[name] = schema.minimum ?? 0
  } else {
    formValues[name] = ''
  }
}

const canSubmit = computed(() =>
  [...required.value].every(name => {
    const value = formValues[name]
    return value !== '' && value !== null && value !== undefined
  }),
)

async function submit() {
  submitting.value = true
  result.value = null
  error.value = null
  try {
    const response = await api.callDemoAction(props.tool.name, { ...formValues })
    if (response.error) {
      error.value = response.error
    } else {
      result.value = response.result
    }
    emit('actionResult', { tool: props.tool.name, result: response.result, error: response.error })
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    emit('actionResult', { tool: props.tool.name, result: null, error: error.value })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.af-card {
  border: 1px solid var(--p-content-border-color, #e2e8f0);
  border-radius: 8px;
  margin-bottom: 0.75rem;
  background: var(--p-content-background, #fff);
}
.af-header {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  width: 100%;
  padding: 0.6rem 0.75rem;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-weight: 600;
}
.af-desc {
  margin: 0 0.75rem 0.5rem;
  font-size: 0.85rem;
  color: var(--p-text-muted-color, #64748b);
}
.af-body {
  padding: 0 0.75rem 0.75rem;
}
.af-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 0.25rem;
}
.af-result {
  margin: 0.5rem 0 0;
  color: #15803d;
  font-size: 0.85rem;
}
.af-error {
  margin: 0.5rem 0 0;
  color: #b91c1c;
  font-size: 0.85rem;
}
</style>
