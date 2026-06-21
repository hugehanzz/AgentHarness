<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { api } from '../api/client'
import type { AgentRun } from '../api/types'

const props = defineProps<{ taskId: number; refreshKey: number }>()
const emit = defineEmits<{
  runsChanged: [runs: AgentRun[]]
}>()

const runs = ref<AgentRun[]>([])
const openDiagnostics = ref<string[]>([])

const latestRun = computed(() => runs.value[0] || null)
const latestRunIsRunning = computed(() => latestRun.value?.status === 'RUNNING')
const latestDiagnostics = computed(() => latestRun.value?.stderr || latestRun.value?.error_message || '')
const diagnosticsLabel = computed(() => {
  if (!latestRun.value?.error_message) return 'Diagnostics'
  return 'Diagnostics · error'
})
const openRunDetails = ref<string[]>([])
const pollIntervalMs = 5000
const maxPollingMs = 10 * 60 * 1000
let pollTimer: ReturnType<typeof window.setInterval> | null = null
let pollStartedAt = 0

const runTypeLabels: Record<string, string> = {
  codex_plan: 'Codex 生成计划',
  codex_implement: 'Codex 执行开发',
  claude_review: 'Claude 代码评审',
  codex_fix: 'Codex 修复问题',
  claude_recheck: 'Claude 复审结果',
  codex_acceptance_checklist: 'Codex 生成验收建议',
  codex_archive: 'Codex README 归档',
}

const providerLabels: Record<string, string> = {
  codex_app_server: 'Codex App Server',
  local_cli: 'Local CLI',
  claude_cli: 'Claude CLI',
}

function runTypeLabel(runType: string) {
  return runTypeLabels[runType] || runType
}

function providerLabel(providerType: string) {
  return providerLabels[providerType] || providerType
}

function tagType(status: AgentRun['status']) {
  if (status === 'SUCCEEDED') return 'success'
  if (status === 'FAILED' || status === 'TIMED_OUT') return 'danger'
  if (status === 'RUNNING') return 'warning'
  return 'info'
}

async function loadRuns() {
  const { data } = await api.get<AgentRun[]>(`/tasks/${props.taskId}/agent-runs`)
  runs.value = data
  emit('runsChanged', data)
}

function stopPolling() {
  if (!pollTimer) return
  window.clearInterval(pollTimer)
  pollTimer = null
  pollStartedAt = 0
}

function startPolling() {
  if (pollTimer) return
  pollStartedAt = Date.now()
  // Runs are executed by external processes; polling keeps the UI fresh without
  // requiring a websocket channel for every AgentRun.
  pollTimer = window.setInterval(() => {
    if (Date.now() - pollStartedAt >= maxPollingMs) {
      stopPolling()
      return
    }
    loadRuns()
  }, pollIntervalMs)
}

onMounted(loadRuns)

onBeforeUnmount(stopPolling)

watch(
  () => props.refreshKey,
  () => {
    loadRuns()
  },
)

watch(
  () => latestRun.value?.id,
  () => {
    // Collapse old diagnostics/details when a new run arrives so evidence from
    // the previous run is not visually mixed with the latest execution.
    openDiagnostics.value = []
    openRunDetails.value = []
  },
)

watch(
  latestRunIsRunning,
  (isRunning) => {
    if (isRunning) {
      startPolling()
    } else {
      stopPolling()
    }
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
      <div class="run-summary">
        <el-tag :type="tagType(latestRun.status)">{{ latestRun.status }}</el-tag>
        <span class="run-title">{{ runTypeLabel(latestRun.run_type) }}</span>
      </div>
      <el-collapse v-model="openRunDetails" class="run-details-collapse">
        <el-collapse-item title="Run details" name="details">
          <div class="run-details">
            <div>
              <span class="detail-label">Provider</span>
              <span>{{ providerLabel(latestRun.provider_type) }}</span>
            </div>
            <div v-if="latestRun.external_thread_id">
              <span class="detail-label">Thread</span>
              <span>{{ latestRun.external_thread_id }}</span>
            </div>
            <div v-if="latestRun.external_turn_id">
              <span class="detail-label">Turn</span>
              <span>{{ latestRun.external_turn_id }}</span>
            </div>
            <div v-if="latestRun.exit_code !== null">
              <span class="detail-label">Exit</span>
              <span>{{ latestRun.exit_code }}</span>
            </div>
            <div>
              <span class="detail-label">Command</span>
              <span>{{ latestRun.command_display || 'No command display' }}</span>
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
      <div v-if="latestRun.output_payload" class="output-box" style="margin-top: 8px;">{{ latestRun.output_payload }}</div>
      <el-collapse v-if="latestDiagnostics" v-model="openDiagnostics" class="diagnostics-collapse">
        <el-collapse-item :title="diagnosticsLabel" name="diagnostics">
          <div class="output-box diagnostics-output">{{ latestDiagnostics }}</div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </div>
</template>

<style scoped>
.run-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.run-title {
  min-width: 0;
  color: #334155;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-details-collapse {
  margin-top: 4px;
  border-top: 0;
  border-bottom: 0;
}

.run-details-collapse :deep(.el-collapse-item__header) {
  height: 32px;
  border-bottom: 0;
  color: var(--muted);
  font-size: 13px;
  font-weight: 650;
}

.run-details-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: 0;
}

.run-details-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 4px;
}

.run-details {
  display: grid;
  gap: 6px;
  padding: 8px 10px;
  border: 1px solid var(--line);
  border-radius: 6px;
  background: #f9fbfd;
  color: #475569;
  font-size: 12px;
  line-height: 1.45;
  word-break: break-word;
}

.run-details > div {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 8px;
}

.detail-label {
  color: var(--muted);
  font-weight: 700;
}

.diagnostics-collapse {
  margin-top: 8px;
  border-top: 0;
  border-bottom: 0;
}

.diagnostics-collapse :deep(.el-collapse-item__header) {
  height: 32px;
  border-bottom: 0;
  color: var(--muted);
  font-size: 13px;
  font-weight: 650;
}

.diagnostics-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: 0;
}

.diagnostics-collapse :deep(.el-collapse-item__content) {
  padding-bottom: 0;
}

.diagnostics-output {
  margin-top: 0;
  max-height: 280px;
}
</style>
