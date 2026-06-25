<template>
  <router-view />
  <FloatingAgentDock />
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted } from 'vue'
import FloatingAgentDock from './components/FloatingAgentDock.vue'
import { useTasksStore } from './stores/tasks'

const store = useTasksStore()

onMounted(() => store.startWorkerPolling())
onBeforeUnmount(() => store.stopWorkerPolling())
</script>
