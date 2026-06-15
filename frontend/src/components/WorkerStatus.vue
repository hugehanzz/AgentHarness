<script setup lang="ts">
import { onMounted } from 'vue'
import { Cpu, Refresh, User, View } from '@element-plus/icons-vue'
import { useTasksStore } from '../stores/tasks'

const store = useTasksStore()

function isHumanSupervisor(workerName: string) {
  return workerName === 'Human Supervisor'
}

function displayStatus(worker: { name: string; status: string; is_online: boolean }) {
  if (isHumanSupervisor(worker.name)) return 'ONLINE'
  return worker.is_online ? worker.status : 'OFFLINE'
}

function isDisplayOnline(worker: { name: string; is_online: boolean }) {
  return isHumanSupervisor(worker.name) || worker.is_online
}

onMounted(() => store.fetchWorkers())
</script>

<template>
  <div class="panel worker-card">
    <div class="panel-header">
      <div>
        <h2 class="panel-title">Workers</h2>
      </div>
      <el-button class="icon-button" :icon="Refresh" circle @click="store.fetchWorkers" />
    </div>
    <div class="registry-table">
      <div class="registry-head">
        <span>Name</span>
        <span>Role</span>
        <span>Status</span>
      </div>
      <div v-if="store.workers.length === 0" class="registry-empty">No Data</div>
      <div v-for="worker in store.workers" :key="worker.id" class="registry-row">
        <span>{{ worker.name }}</span>
        <span class="registry-role">
          <el-icon>
            <Cpu v-if="worker.role.includes('COMMAND')" />
            <View v-else-if="worker.role.includes('REVIEW')" />
            <User v-else />
          </el-icon>
          {{ worker.role }}
        </span>
        <span :class="['registry-status', isDisplayOnline(worker) ? 'online' : 'offline']">
          <i></i>{{ displayStatus(worker) }}
        </span>
      </div>
    </div>
  </div>
</template>
