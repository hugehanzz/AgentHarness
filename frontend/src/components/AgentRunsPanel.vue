<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { api } from '../api/client'
import type { AgentRun } from '../api/types'

const props = defineProps<{ taskId: number; refreshKey: number }>()

const runs = ref<AgentRun[]>([])

const latestRun = computed(() => runs.value[0] || null)

function tagType(status: AgentRun['status']) {
  if (status === 'SUCCEEDED') return 'success'
  if (status === 'FAILED' || status === 'TIMED_OUT') return 'danger'
  if (status === 'RUNNING') return 'warning'
  return 'info'
}

async function loadRuns() {
  const { data } = await api.get<AgentRun[]>(`/tasks/${props.taskId}/agent-runs`)
  runs.value = data
}

onMounted(loadRuns)

watch(
  () => props.refreshKey,
  () => {
    loadRuns()
  },
)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div>
        <h2 class="panel-title">Agent Runs</h2>
        <div class="panel-kicker">Execution history and evidence</div>
      </div>
      <el-button class="icon-button" circle :icon="Refresh" @click="loadRuns" />
    </div>

    <div v-if="latestRun" style="margin-top: 12px;">
      <div class="copy-row">
        <el-tag :type="tagType(latestRun.status)">{{ latestRun.status }}</el-tag>
        <span class="muted">{{ latestRun.run_type }}</span>
        <span class="muted">{{ latestRun.provider_type }}</span>
        <span class="muted" v-if="latestRun.external_thread_id">thread {{ latestRun.external_thread_id }}</span>
        <span class="muted" v-if="latestRun.exit_code !== null">exit {{ latestRun.exit_code }}</span>
      </div>
      <div class="muted" style="margin-top: 8px;">{{ latestRun.command_display || 'No command display' }}</div>
      <div v-if="latestRun.output_payload" class="output-box" style="margin-top: 8px;">{{ latestRun.output_payload }}</div>
      <div v-if="latestRun.stderr || latestRun.error_message" class="output-box" style="margin-top: 8px;">
        {{ latestRun.stderr || latestRun.error_message }}
      </div>
    </div>
  </div>
</template>
