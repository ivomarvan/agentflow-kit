<template>
  <div class="app-container">
    <div class="app-header">
      <h1>{{ appInfo?.name ?? 'agentflow GUI' }}</h1>
      <span class="app-description">{{ appInfo?.description ?? '' }}</span>
    </div>
    <Tabs value="chat">
      <TabList>
        <Tab value="chat">💬 Chat</Tab>
        <Tab value="settings" disabled>⚙️ Settings</Tab>
        <Tab value="structure" disabled>🔗 Structure</Tab>
      </TabList>
      <TabPanels>
        <TabPanel value="chat">
          <ChatView />
        </TabPanel>
        <TabPanel value="settings">
          <p class="coming-soon">Settings — coming in E099</p>
        </TabPanel>
        <TabPanel value="structure">
          <p class="coming-soon">Structure — coming in E099</p>
        </TabPanel>
      </TabPanels>
    </Tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Tabs, TabList, Tab, TabPanels, TabPanel } from 'primevue'
import ChatView from '@/components/chat/ChatView.vue'
import { api } from '@/services/api'

const appInfo = ref<{ name: string; description: string } | null>(null)

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
.coming-soon {
  padding: 2rem;
  text-align: center;
  color: var(--p-text-muted-color, #999);
}
</style>
