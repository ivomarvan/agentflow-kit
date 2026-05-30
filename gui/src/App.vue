<template>
  <div class="app-container">
    <div class="app-header">
      <h1>{{ appInfo?.name ?? 'agentflow GUI' }}</h1>
      <span class="app-description">{{ appInfo?.description ?? '' }}</span>
    </div>
    <Tabs v-model:value="activeTab">
      <TabList>
        <Tab value="chat">💬 Chat</Tab>
        <Tab value="voicebot">🎤 VoiceBot</Tab>
        <Tab value="settings">⚙️ Settings</Tab>
        <Tab value="structure">🔗 Structure</Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="chat">
          <ChatView />
        </TabPanel>
        <TabPanel value="voicebot">
          <VoiceBotView />
        </TabPanel>
        <TabPanel value="settings">
          <SettingsView />
        </TabPanel>
        <TabPanel value="structure">
          <StructureView @nodeClick="onNodeClick" />
        </TabPanel>
      </TabPanels>
    </Tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Tabs, TabList, Tab, TabPanels, TabPanel } from 'primevue'
import ChatView from '@/components/chat/ChatView.vue'
import VoiceBotView from '@/components/voicebot/VoiceBotView.vue'
import SettingsView from '@/components/settings/SettingsView.vue'
import StructureView from '@/components/structure/StructureView.vue'
import { api } from '@/services/api'

const appInfo = ref<{ name: string; description: string } | null>(null)
const activeTab = ref('chat')

onMounted(async () => {
  try {
    appInfo.value = await api.getInfo()
  } catch {
    // server not available yet
  }
})

/** Switch to Settings tab so the user can inspect parameters for the clicked node. */
function onNodeClick(_nodeId: string) {
  activeTab.value = 'settings'
}
</script>

<style scoped>
.app-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem;
  font-family: system-ui, sans-serif;
}
.app-header {
  display: flex;
  align-items: baseline;
  gap: 1rem;
  margin-bottom: 1rem;
}
.app-header h1 {
  margin: 0;
  font-size: 1.5rem;
}
.app-description {
  color: var(--p-text-muted-color, #666);
  font-size: 0.9rem;
}
</style>
