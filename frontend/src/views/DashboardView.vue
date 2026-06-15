<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Connection, FolderOpened, List, Plus, Refresh, Share, UserFilled } from '@element-plus/icons-vue'
import FolderPickerDialog from '../components/FolderPickerDialog.vue'
import WorkerStatus from '../components/WorkerStatus.vue'
import { useTasksStore } from '../stores/tasks'

const store = useTasksStore()
const router = useRouter()
const folderPickerVisible = ref(false)
const form = reactive({
  title: '',
  description: '',
  workspace_path: '',
})

async function createTask() {
  if (!form.title.trim() || !form.description.trim()) return
  await store.createTask({
    title: form.title,
    description: form.description,
    workspace_path: form.workspace_path || undefined,
  })
  form.title = ''
  form.description = ''
  form.workspace_path = ''
}

const runningTasks = computed(() =>
  store.tasks.filter((task) => !['DONE', 'ARCHIVED'].includes(task.status)).length,
)

const gateTasks = computed(() =>
  store.tasks.filter((task) => ['PLAN_READY', 'ACCEPTANCE_READY'].includes(task.status)).length,
)

const onlineWorkers = computed(() =>
  store.workers.filter((worker) => worker.is_online || worker.name === 'Human Supervisor').length,
)

function formatTimestamp(value: string) {
  return value.replace('T', ' ')
}

onMounted(() => {
  store.fetchTasks()
  store.fetchWorkers()
})
</script>

<template>
  <div class="layout">
    <header class="topbar">
      <div class="brand-block">
        <div class="brand-mark" aria-hidden="true">
          <span></span>
          <span></span>
        </div>
        <div>
          <div class="brand">AgentHarness</div>
          <div class="brand-subtitle">Local multi-agent R&amp;D workflow controller</div>
        </div>
      </div>
      <div class="toolbar">
        <div class="status-hub">
          <strong>{{ onlineWorkers }}/{{ store.workers.length || 0 }}</strong>
          <div>
            <div>Worker Status Hub</div>
            <span><i></i>{{ onlineWorkers }} Workers Online</span>
          </div>
          <el-icon><Connection /></el-icon>
        </div>
        <el-button class="soft-button" :icon="Refresh" @click="store.fetchTasks">Refresh</el-button>
      </div>
    </header>

    <main class="content page-grid dashboard-grid">
      <section class="grid dashboard-left">
        <div class="panel">
          <div class="panel-header">
            <div>
              <h2 class="panel-title">New Requirement</h2>
            </div>
          </div>
          <el-form label-position="top">
            <el-form-item label="Title">
              <el-input v-model="form.title" placeholder="例如：员工请假审批流程优化" />
            </el-form-item>
            <el-form-item label="Workspace Path">
              <el-input v-model="form.workspace_path" placeholder="D:\project\workspace">
                <template #append>
                  <el-button class="folder-trigger" :icon="FolderOpened" @click="folderPickerVisible = true" />
                </template>
              </el-input>
            </el-form-item>
            <el-form-item label="Description">
              <el-input v-model="form.description" type="textarea" :rows="7" placeholder="请描述需求背景、目标、约束、风险点和验收标准。" />
            </el-form-item>
            <el-button class="primary-action" type="primary" :icon="Plus" @click="createTask">Create Workflow</el-button>
          </el-form>
        </div>
        <WorkerStatus />
      </section>

      <section class="panel workflow-board-panel">
        <div class="panel-header">
          <div>
            <h2 class="panel-title">Workflow Board</h2>
          </div>
        </div>

        <div class="metric-row">
          <div class="metric">
            <div>
              <div class="metric-value">{{ store.tasks.length }}</div>
              <div class="metric-label">Total Tasks</div>
            </div>
            <div class="metric-icon">
              <el-icon><List /></el-icon>
            </div>
          </div>
          <div class="metric">
            <div>
              <div class="metric-value">{{ runningTasks }}</div>
              <div class="metric-label">Active Flows</div>
            </div>
            <div class="metric-icon">
              <el-icon><Share /></el-icon>
            </div>
          </div>
          <div class="metric">
            <div>
              <div class="metric-value">{{ gateTasks }}</div>
              <div class="metric-label">Human Gates</div>
            </div>
            <div class="metric-icon">
              <el-icon><UserFilled /></el-icon>
            </div>
          </div>
        </div>

        <el-table class="workflow-table" :data="store.tasks" height="100%" @row-click="(row: any) => router.push(`/tasks/${row.id}`)">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column label="Task" min-width="260">
            <template #default="{ row }">
              <div class="task-title-cell">
                <strong>{{ row.title }}</strong>
                <span>{{ row.workspace_path || 'No workspace path' }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="Status" min-width="190">
            <template #default="{ row }">
              <span class="status-pill">{{ row.status }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Priority" width="130">
            <template #default="{ row }">
              <span :class="['priority-pill', `priority-${row.priority}`]">{{ row.priority }}</span>
            </template>
          </el-table-column>
          <el-table-column label="Updated" min-width="180">
            <template #default="{ row }">
              {{ formatTimestamp(row.updated_at) }}
            </template>
          </el-table-column>
        </el-table>
      </section>
    </main>
    <FolderPickerDialog
      v-model="folderPickerVisible"
      :initial-path="form.workspace_path"
      @select="(path) => (form.workspace_path = path)"
    />
  </div>
</template>
