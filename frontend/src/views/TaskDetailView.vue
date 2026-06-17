<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Check, Close, Edit, Refresh, Right } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import AcceptancePanel from '../components/AcceptancePanel.vue'
import AgentRunsPanel from '../components/AgentRunsPanel.vue'
import CommandPanel from '../components/CommandPanel.vue'
import PromptPanel from '../components/PromptPanel.vue'
import ReviewPanel from '../components/ReviewPanel.vue'
import WorkerStatus from '../components/WorkerStatus.vue'
import { api } from '../api/client'
import { useTasksStore } from '../stores/tasks'
import type { AgentRun, TaskStatus } from '../api/types'

const route = useRoute()
const router = useRouter()
const store = useTasksStore()
const taskId = Number(route.params.id)
const requirementEditing = ref(false)
const requirementSaving = ref(false)
const requirementDraft = ref('')
const flowActionRunning = ref<TaskStatus | null>(null)
const currentAgentRunning = ref(false)
const agentRunsRefreshKey = ref(0)

const statuses: TaskStatus[] = [
  'REQUIREMENT_DRAFT',
  'PLAN_REQUESTED',
  'PLAN_READY',
  'PLAN_CONFIRMED',
  'IMPLEMENTING',
  'IMPLEMENT_DONE',
  'REVIEW_REQUESTED',
  'REVIEW_DONE',
  'FIX_REQUIRED',
  'FIXING',
  'FIX_DONE',
  'RECHECK_REQUESTED',
  'RECHECK_DONE',
  'ACCEPTANCE_READY',
  'ACCEPTANCE_PASSED',
  'ARCHIVED',
  'DONE',
]

const nextStatusMap: Partial<Record<TaskStatus, TaskStatus[]>> = {
  REQUIREMENT_DRAFT: ['PLAN_REQUESTED'],
  PLAN_REQUESTED: ['PLAN_READY'],
  PLAN_READY: ['PLAN_CONFIRMED'],
  PLAN_CONFIRMED: ['IMPLEMENTING'],
  IMPLEMENTING: ['IMPLEMENT_DONE'],
  IMPLEMENT_DONE: ['REVIEW_REQUESTED'],
  REVIEW_REQUESTED: ['REVIEW_DONE'],
  REVIEW_DONE: ['FIX_REQUIRED', 'ACCEPTANCE_READY'],
  FIX_REQUIRED: ['FIXING'],
  FIXING: ['FIX_DONE'],
  FIX_DONE: ['RECHECK_REQUESTED'],
  RECHECK_REQUESTED: ['RECHECK_DONE'],
  RECHECK_DONE: ['FIX_REQUIRED', 'ACCEPTANCE_READY'],
  ACCEPTANCE_READY: ['ACCEPTANCE_PASSED'],
  ACCEPTANCE_PASSED: ['ARCHIVED'],
  ARCHIVED: ['DONE'],
}

const compactStages: Array<{ label: string; statuses: TaskStatus[] }> = [
  { label: 'Requirement', statuses: ['REQUIREMENT_DRAFT'] },
  { label: 'Plan', statuses: ['PLAN_REQUESTED', 'PLAN_READY', 'PLAN_CONFIRMED'] },
  { label: 'Build', statuses: ['IMPLEMENTING', 'IMPLEMENT_DONE'] },
  { label: 'Review', statuses: ['REVIEW_REQUESTED', 'REVIEW_DONE'] },
  { label: 'Fix', statuses: ['FIX_REQUIRED', 'FIXING', 'FIX_DONE'] },
  { label: 'Recheck', statuses: ['RECHECK_REQUESTED', 'RECHECK_DONE'] },
  { label: 'Accept', statuses: ['ACCEPTANCE_READY', 'ACCEPTANCE_PASSED'] },
  { label: 'Archive', statuses: ['ARCHIVED'] },
  { label: 'Done', statuses: ['DONE'] },
]

const activeStageIndex = computed(() => {
  if (!store.selectedTask) return 0
  const index = compactStages.findIndex((stage) => stage.statuses.includes(store.selectedTask!.status))
  return index >= 0 ? index : 0
})

const nextStatuses = computed(() => {
  if (!store.selectedTask) return []
  return nextStatusMap[store.selectedTask.status] || []
})

const requirementChanged = computed(() => {
  return requirementDraft.value.trim() !== (store.selectedTask?.description || '').trim()
})

const actionLabels: Partial<Record<TaskStatus, string>> = {
  PLAN_REQUESTED: '请求计划',
  PLAN_READY: '计划已准备',
  PLAN_CONFIRMED: '确认计划',
  IMPLEMENTING: '开始开发',
  IMPLEMENT_DONE: '标记开发完成',
  REVIEW_REQUESTED: '请求评审',
  REVIEW_DONE: '标记评审完成',
  FIX_REQUIRED: '要求修复',
  FIXING: '开始修复',
  FIX_DONE: '标记修复完成',
  RECHECK_REQUESTED: '请求复审',
  RECHECK_DONE: '标记复审完成',
  ACCEPTANCE_READY: '进入验收',
  ACCEPTANCE_PASSED: '标记验收通过',
  ARCHIVED: '归档任务',
  DONE: '标记完成',
}

const statusLabels: Record<TaskStatus, string> = {
  REQUIREMENT_DRAFT: '需求草稿',
  PLAN_REQUESTED: '请求计划',
  PLAN_READY: '计划待确认',
  PLAN_CONFIRMED: '计划已确认',
  IMPLEMENTING: '开发中',
  IMPLEMENT_DONE: '开发完成',
  REVIEW_REQUESTED: '请求评审',
  REVIEW_DONE: '评审完成',
  FIX_REQUIRED: '需要修复',
  FIXING: '修复中',
  FIX_DONE: '修复完成',
  RECHECK_REQUESTED: '请求复审',
  RECHECK_DONE: '复审完成',
  ACCEPTANCE_READY: '待验收',
  ACCEPTANCE_PASSED: '验收通过',
  ARCHIVED: '已归档',
  DONE: '完成',
}

const eventTypeLabels: Record<string, string> = {
  TASK_CREATED: '任务创建',
  TASK_TRANSITIONED: '流程流转',
  REQUIREMENT_UPDATED: '需求更新',
  AGENT_RUN_COMPLETED: 'Agent Run',
}

const agentRunByTransition: Partial<Record<TaskStatus, string>> = {
  PLAN_REQUESTED: 'codex_plan',
  IMPLEMENTING: 'codex_implement',
  REVIEW_REQUESTED: 'claude_review',
  FIXING: 'codex_fix',
  RECHECK_REQUESTED: 'claude_recheck',
}

const agentRunByCurrentStatus: Partial<Record<TaskStatus, string>> = {
  PLAN_REQUESTED: 'codex_plan',
  IMPLEMENTING: 'codex_implement',
  REVIEW_REQUESTED: 'claude_review',
  FIXING: 'codex_fix',
  RECHECK_REQUESTED: 'claude_recheck',
}

const agentRunLabels: Record<string, string> = {
  codex_plan: '运行 Codex Plan',
  codex_implement: '运行 Codex Implement',
  claude_review: '运行 Claude Review',
  codex_fix: '运行 Codex Fix',
  claude_recheck: '运行 Claude Recheck',
}

const currentAgentRunType = computed(() => {
  if (!store.selectedTask) return null
  return agentRunByCurrentStatus[store.selectedTask.status] || null
})

function actionLabel(status: TaskStatus) {
  return actionLabels[status] || status
}

function statusLabel(status: TaskStatus | null) {
  return status ? statusLabels[status] || status : '-'
}

function eventTypeLabel(type: string) {
  return eventTypeLabels[type] || type
}

function eventTitle(event: { event_type: string; from_status: TaskStatus | null; to_status: TaskStatus | null }) {
  if (event.event_type === 'TASK_TRANSITIONED') {
    return `${statusLabel(event.from_status)} -> ${statusLabel(event.to_status)}`
  }
  if (event.event_type === 'TASK_CREATED') {
    return `${eventTypeLabel(event.event_type)} -> ${statusLabel(event.to_status)}`
  }
  return eventTypeLabel(event.event_type)
}

function formatTimestamp(value: string) {
  return value.replace('T', ' ')
}

function stageState(stageIndex: number) {
  if (!store.selectedTask) return ''
  if (activeStageIndex.value === stageIndex) return 'is-active'
  if (activeStageIndex.value > stageIndex) return 'is-done'
  return ''
}

async function loadTask() {
  try {
    await store.fetchTask(taskId)
  } catch {
    // The template shows store.detailError instead of rendering a blank page.
  }
}

function refreshAgentRuns() {
  agentRunsRefreshKey.value += 1
}

async function runAgentByType(runType: string) {
  const { data } = await api.post<AgentRun>(`/tasks/${taskId}/agent-runs`, { run_type: runType })
  refreshAgentRuns()
  ElMessage.success(`${runType} finished with ${data.status}`)
}

async function runAgentForTransition(toStatus: TaskStatus) {
  const runType = agentRunByTransition[toStatus]
  if (!runType) return

  await runAgentByType(runType)
}

async function runCurrentAgent() {
  if (!currentAgentRunType.value) return
  currentAgentRunning.value = true
  try {
    await runAgentByType(currentAgentRunType.value)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || 'Agent run failed')
  } finally {
    currentAgentRunning.value = false
  }
}

async function transition(toStatus: TaskStatus) {
  flowActionRunning.value = toStatus
  const previousStatus = store.selectedTask?.status
  try {
    await store.transitionTask(taskId, toStatus, `Human Supervisor: ${actionLabel(toStatus)}`)
    if (store.selectedTask?.status && store.selectedTask.status !== previousStatus) {
      refreshAgentRuns()
    }
    await runAgentForTransition(toStatus)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || 'Flow action failed')
  } finally {
    flowActionRunning.value = null
  }
}

function startRequirementEdit() {
  requirementDraft.value = store.selectedTask?.description || ''
  requirementEditing.value = true
}

function cancelRequirementEdit() {
  requirementDraft.value = store.selectedTask?.description || ''
  requirementEditing.value = false
}

async function saveRequirement() {
  if (!requirementChanged.value || !requirementDraft.value.trim()) return
  requirementSaving.value = true
  try {
    await store.updateRequirement(taskId, requirementDraft.value)
    requirementEditing.value = false
  } finally {
    requirementSaving.value = false
  }
}

watch(
  () => store.selectedTask?.description,
  (description) => {
    if (!requirementEditing.value) {
      requirementDraft.value = description || ''
    }
  },
  { immediate: true },
)

onMounted(() => {
  loadTask()
  store.fetchWorkers()
})
</script>

<template>
  <div class="layout" v-if="store.detailLoading">
    <header class="topbar">
      <div>
        <el-button :icon="ArrowLeft" text @click="router.push('/')">Back</el-button>
        <span class="brand">Loading Task</span>
        <div class="brand-subtitle">Fetching workflow detail</div>
      </div>
    </header>
    <main class="content">
      <div class="panel">
        <el-skeleton :rows="8" animated />
      </div>
    </main>
  </div>

  <div class="layout" v-else-if="store.detailError || !store.selectedTask">
    <header class="topbar">
      <div>
        <el-button :icon="ArrowLeft" text @click="router.push('/')">Back</el-button>
        <span class="brand">Task Detail Unavailable</span>
        <div class="brand-subtitle">The workflow detail request did not complete</div>
      </div>
    </header>
    <main class="content">
      <div class="panel">
        <div class="panel-header">
          <div>
            <h2 class="panel-title">Cannot load task detail</h2>
            <div class="panel-kicker">Check backend service, task id, and browser console.</div>
          </div>
        </div>
        <el-alert
          :title="store.detailError || 'Task detail is empty'"
          type="error"
          show-icon
          :closable="false"
        />
        <div class="copy-row" style="margin-top: 16px;">
          <el-button :icon="ArrowLeft" @click="router.push('/')">Back to Workflow Board</el-button>
          <el-button type="primary" :icon="Refresh" @click="loadTask">Retry</el-button>
        </div>
      </div>
    </main>
  </div>

  <div class="layout" v-else>
    <header class="topbar detail-topbar">
      <div class="detail-title-block">
        <div class="detail-title-row">
          <el-button :icon="ArrowLeft" text @click="router.push('/')">Back</el-button>
          <span class="brand">{{ store.selectedTask.title }}</span>
        </div>
        <div class="brand-subtitle">{{ store.selectedTask.workspace_path || 'No workspace path configured' }}</div>
      </div>
      <div class="toolbar">
        <el-tag class="detail-status-tag" type="primary" effect="plain">{{ statusLabel(store.selectedTask.status) }}</el-tag>
        <el-button :icon="Refresh" @click="loadTask">Refresh</el-button>
      </div>
    </header>

    <main class="content grid">
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2 class="panel-title">Flow State</h2>
          </div>
          <span class="status-pill">{{ activeStageIndex + 1 }} / {{ compactStages.length }}</span>
        </div>

        <div class="workflow-strip">
          <div
            v-for="(stage, index) in compactStages"
            :key="stage.label"
            :class="['workflow-step', stageState(index)]"
          >
            <div class="workflow-index">0{{ index + 1 }}</div>
            <div class="workflow-label">{{ stage.label }}</div>
          </div>
        </div>

        <div class="copy-row" style="margin-top: 16px;">
          <el-button
            v-for="status in nextStatuses"
            :key="status"
            type="primary"
            :icon="status === 'ACCEPTANCE_PASSED' ? Check : Right"
            :loading="flowActionRunning === status"
            :disabled="Boolean(flowActionRunning)"
            @click="transition(status)"
          >
            {{ actionLabel(status) }}
          </el-button>
          <el-button
            v-if="currentAgentRunType"
            :icon="Right"
            :loading="currentAgentRunning"
            :disabled="Boolean(flowActionRunning) || currentAgentRunning"
            @click="runCurrentAgent"
          >
            {{ agentRunLabels[currentAgentRunType] || currentAgentRunType }}
          </el-button>
        </div>
      </section>

      <section class="grid detail-main">
        <div class="grid">
          <div class="panel">
            <div class="panel-header">
              <div>
                <h2 class="panel-title">Requirement</h2>
                <div class="panel-kicker">Source material for prompt generation</div>
              </div>
              <el-button
                v-if="!requirementEditing"
                class="icon-button"
                :icon="Edit"
                @click="startRequirementEdit"
              >
                Edit
              </el-button>
            </div>
            <div v-if="!requirementEditing" class="requirement-text">{{ store.selectedTask.description }}</div>
            <div v-else class="requirement-editor">
              <el-input
                v-model="requirementDraft"
                type="textarea"
                :rows="5"
                resize="vertical"
                placeholder="Describe the requirement, goals, constraints, risks, and acceptance criteria."
              />
              <div class="copy-row">
                <el-button :icon="Close" @click="cancelRequirementEdit">Cancel</el-button>
                <el-button
                  type="primary"
                  :icon="Check"
                  :loading="requirementSaving"
                  :disabled="!requirementChanged || !requirementDraft.trim()"
                  @click="saveRequirement"
                >
                  Save
                </el-button>
              </div>
            </div>
          </div>
          <AgentRunsPanel :task-id="taskId" :refresh-key="agentRunsRefreshKey" />
          <WorkerStatus />
          <AcceptancePanel :task-id="taskId" />
        </div>

        <div class="grid">
          <PromptPanel :task-id="taskId" :current-status="store.selectedTask.status" />
          <ReviewPanel :task-id="taskId" :workspace-path="store.selectedTask.workspace_path" />
          <CommandPanel :task-id="taskId" :workspace-path="store.selectedTask.workspace_path" />
          <div class="panel">
            <div class="panel-header">
              <div>
                <h2 class="panel-title">Events</h2>
              </div>
            </div>
            <el-timeline>
              <el-timeline-item v-for="event in store.events" :key="event.id" :timestamp="formatTimestamp(event.created_at)">
                {{ eventTitle(event) }}
                <div class="muted">{{ event.message }}</div>
              </el-timeline-item>
            </el-timeline>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
