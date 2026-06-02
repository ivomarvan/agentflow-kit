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
          <StructureView />
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
import StickyMarkdownTooltipTitle from '@/components/ui/StickyMarkdownTooltipTitle.vue'
import { api } from '@/services/api'

const appInfo = ref<{ name: string; doc: string } | null>(null)
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
  max-width: 1200px;
  margin: 0 auto;
  padding: 1rem;
  font-family: system-ui, sans-serif;
}
.app-header {
  margin-bottom: 1rem;
}
</style>
