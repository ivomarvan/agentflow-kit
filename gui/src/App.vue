<template>
  <DemoView v-if="isDemoMode" />
  <div v-else class="app-container">
    <Tabs v-model:value="activeTab">
      <!-- Title and tab selector share one responsive row -->
      <div class="app-top-row">
        <StickyMarkdownTooltipTitle
          :title="appInfo?.name ?? 'agentflow GUI'"
          :doc="appInfo?.doc ?? ''"
        />
        <div class="tab-list-wrapper">
          <TabList>
            <Tab
              value="chat"
              v-tooltip.bottom="{
                value: 'Conversation with the agent — type questions, receive answers, view run events',
                showDelay: 500
              }"
            >💬 Chat</Tab>
            <Tab
              value="inspector"
              v-tooltip.bottom="{
                value: 'Agent graph and parameters — visualize the graph, inspect and edit vertex configuration',
                showDelay: 500
              }"
            >🔍 Inspector</Tab>
            <Tab
              value="settings"
              v-tooltip.bottom="{
                value: 'Application preferences — voice input/output, STT/TTS language and other settings',
                showDelay: 500
              }"
            >⚙️ Settings</Tab>
          </TabList>
        </div>
      </div>
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
import DemoView from '@/views/DemoView.vue'
import StickyMarkdownTooltipTitle from '@/components/ui/StickyMarkdownTooltipTitle.vue'
import { api } from '@/services/api'

const isDemoMode = window.location.pathname === '/demo' || window.location.search.includes('mode=demo')

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

/* Title + tabs on one line; wraps to two lines on narrow screens */
.app-top-row {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  flex-wrap: wrap;
}

/* Tab list fills remaining space next to the title */
.tab-list-wrapper {
  flex: 1;
  min-width: 0;
}
</style>
