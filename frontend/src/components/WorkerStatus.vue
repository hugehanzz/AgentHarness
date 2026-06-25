<script setup lang="ts">
import { Cpu, Refresh, User, View } from '@element-plus/icons-vue'
import { useTasksStore } from '../stores/tasks'

const store = useTasksStore()

function statusClass(status: string) {
  return status.toLowerCase()
}

function heartbeatTitle(value: string | null) {
  return value ? `Last heartbeat: ${value.replace('T', ' ')}` : 'No heartbeat'
}

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
            <Cpu v-if="worker.worker_key === 'codex'" />
            <View v-else-if="worker.worker_key === 'claude'" />
            <User v-else />
          </el-icon>
          {{ worker.role }}
        </span>
        <span
          :class="['registry-status', statusClass(worker.status)]"
          :title="heartbeatTitle(worker.last_heartbeat_at)"
        >
          <i></i>{{ worker.status }}
        </span>
      </div>
    </div>
  </div>
</template>
