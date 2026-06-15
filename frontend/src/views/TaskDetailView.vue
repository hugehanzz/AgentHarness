<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Check, Refresh, Right } from '@element-plus/icons-vue'
import AcceptancePanel from '../components/AcceptancePanel.vue'
import CommandPanel from '../components/CommandPanel.vue'
import PromptPanel from '../components/PromptPanel.vue'
import ReviewPanel from '../components/ReviewPanel.vue'
import WorkerStatus from '../components/WorkerStatus.vue'
import { useTasksStore } from '../stores/tasks'
import type { TaskStatus } from '../api/types'

const route = useRoute()
const router = useRouter()
const store = useTasksStore()
const taskId = Number(route.params.id)

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

const compactStages: Array<{ label: string; status: TaskStatus }> = [
  { label: 'Requirement', status: 'REQUIREMENT_DRAFT' },
  { label: 'Plan', status: 'PLAN_READY' },
  { label: 'Build', status: 'IMPLEMENT_DONE' },
  { label: 'Review', status: 'REVIEW_DONE' },
  { label: 'Fix', status: 'FIX_DONE' },
  { label: 'Recheck', status: 'RECHECK_DONE' },
  { label: 'Accept', status: 'ACCEPTANCE_READY' },
  { label: 'Archive', status: 'ARCHIVED' },
  { label: 'Done', status: 'DONE' },
]

const activeStep = computed(() => {
  if (!store.selectedTask) return 0
  return statuses.indexOf(store.selectedTask.status)
})

const nextStatuses = computed(() => {
  if (!store.selectedTask) return []
  return nextStatusMap[store.selectedTask.status] || []
})

function stageState(stageStatus: TaskStatus) {
  const stageIndex = statuses.indexOf(stageStatus)
  if (!store.selectedTask) return ''
  if (store.selectedTask.status === stageStatus) return 'is-active'
  if (activeStep.value >= stageIndex) return 'is-done'
  return ''
}

async function transition(toStatus: TaskStatus) {
  await store.transitionTask(taskId, toStatus, `Human Supervisor moved task to ${toStatus}`)
}

onMounted(() => {
  store.fetchTask(taskId)
  store.fetchWorkers()
})
</script>

<template>
  <div class="layout" v-if="store.selectedTask">
    <header class="topbar">
      <div>
        <el-button :icon="ArrowLeft" text @click="router.push('/')">Back</el-button>
        <span class="brand">{{ store.selectedTask.title }}</span>
        <div class="brand-subtitle">{{ store.selectedTask.workspace_path || 'No workspace path configured' }}</div>
      </div>
      <div class="toolbar">
        <el-tag type="primary" effect="plain">{{ store.selectedTask.status }}</el-tag>
        <el-button :icon="Refresh" @click="store.fetchTask(taskId)">Refresh</el-button>
      </div>
    </header>

    <main class="content grid">
      <section class="panel">
        <div class="panel-header">
          <div>
            <h2 class="panel-title">Flow State</h2>
            <div class="panel-kicker">Human Supervisor remains the gate owner</div>
          </div>
          <span class="status-pill">{{ activeStep + 1 }} / {{ statuses.length }}</span>
        </div>

        <div class="workflow-strip">
          <div
            v-for="(stage, index) in compactStages"
            :key="stage.status"
            :class="['workflow-step', stageState(stage.status)]"
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
            @click="transition(status)"
          >
            {{ status }}
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
            </div>
            <p class="requirement-text">{{ store.selectedTask.description }}</p>
            <div class="path-box">{{ store.selectedTask.workspace_path || 'No workspace path' }}</div>
          </div>
          <WorkerStatus />
          <AcceptancePanel :task-id="taskId" />
        </div>

        <div class="grid">
          <PromptPanel :task-id="taskId" />
          <ReviewPanel :task-id="taskId" :workspace-path="store.selectedTask.workspace_path" />
          <CommandPanel :task-id="taskId" :workspace-path="store.selectedTask.workspace_path" />
          <div class="panel">
            <div class="panel-header">
              <div>
                <h2 class="panel-title">Events</h2>
                <div class="panel-kicker">State transitions and supervisor actions</div>
              </div>
            </div>
            <el-timeline>
              <el-timeline-item v-for="event in store.events" :key="event.id" :timestamp="event.created_at">
                {{ event.event_type }} · {{ event.from_status || '-' }} -> {{ event.to_status || '-' }}
                <div class="muted">{{ event.message }}</div>
              </el-timeline-item>
            </el-timeline>
          </div>
        </div>
      </section>
    </main>
  </div>
</template>
