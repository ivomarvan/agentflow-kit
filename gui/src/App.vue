<template>
  <div class="app-container">
    <div class="app-header">
      <StickyMarkdownTooltipTitle
        :title="appInfo?.name ?? 'agentflow GUI'"
        :doc="appInfo?.doc ?? ''"
      />
    </div>
    <Tabs v-model:value="activeTab">
      <TabList>
        <Tab value="chat">💬 Chat</Tab>
        <Tab value="inspector">🔍 Inspector</Tab>
        <Tab value="settings">⚙️ Settings</Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="chat">
          <ChatView />
        </TabPanel>
        <TabPanel value="inspector">
          <InspectorView />
        </TabPanel>
        <TabPanel value="settings">
          <GUISettingsView />
        </TabPanel>
      </TabPanels>
    </Tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Tabs, TabList, Tab, TabPanels, TabPanel } from 'primevue'
import ChatView from '@/components/chat/ChatView.vue'
import InspectorView from '@/components/inspector/InspectorView.vue'
import GUISettingsView from '@/components/guisettings/GUISettingsView.vue'
import StickyMarkdownTooltipTitle from '@/components/ui/StickyMarkdownTooltipTitle.vue'
import { api } from '@/services/api'

const appInfo  = ref<{ name: string; doc: string } | null>(null)
const activeTab = ref('chat')

onMounted(async () => {
  try {
    appInfo.value = await api.getInfo()
  } catch {
    // server not available yet
  }
})
</script>

<style scoped>
.app-container {
  max-width: 1600px;
  margin: 0 auto;
  padding: 0.4rem 1rem 0.5rem;
  font-family: system-ui, sans-serif;
}
.app-header {
  margin-bottom: 0.3rem;
}
</style>
