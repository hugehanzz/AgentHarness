<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import { api } from '../api/client'

const props = defineProps<{ taskId: number; workspacePath: string | null }>()

const workspacePath = ref(props.workspacePath || '')
const result = ref<any | null>(null)
const loading = ref(false)
const errorMessage = ref('')
const showDetails = ref(false)

function severityText(severity: string) {
  const labels: Record<string, string> = {
    HIGH: '高',
    MEDIUM: '中',
    LOW: '低',
  }
  return labels[severity] || severity
}

function issueStatusText(status: string) {
  const labels: Record<string, string> = {
    OPEN: '待处理',
    FIXED_PENDING_RECHECK: '已修复待复审',
    CLOSED: '已关闭',
    WONT_FIX: '暂不处理',
  }
  return labels[status] || status
}

async function parseReview(revealDetails = true) {
  // REVIEW.md is owned by the reviewer agent in the external workspace. The
  // frontend only asks the backend to parse and mirror it for display.
  if (!workspacePath.value.trim()) {
    showDetails.value = revealDetails
    errorMessage.value = '请先填写工作区路径。'
    ElMessage.warning(errorMessage.value)
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    const { data } = await api.post('/reviews/parse', {
      workspace_path: workspacePath.value.trim(),
      task_id: props.taskId,
    })
    result.value = data
    showDetails.value = revealDetails
  } catch (error: any) {
    result.value = null
    showDetails.value = revealDetails
    errorMessage.value =
      error?.response?.data?.detail || error?.message || 'Review Results 解析失败。'
    ElMessage.error(errorMessage.value)
  } finally {
    loading.value = false
  }
}

watch(
  () => props.workspacePath,
  (value) => {
    if (value && value !== workspacePath.value) {
      workspacePath.value = value
      result.value = null
      errorMessage.value = ''
      showDetails.value = false
    }
  },
)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div>
        <h2 class="panel-title">Review Results</h2>
      </div>
      <el-button
        class="icon-button"
        :icon="Refresh"
        :loading="loading"
        circle
        @click="parseReview(showDetails)"
      />
    </div>
    <el-input
      v-model="workspacePath"
      placeholder="Workspace path"
      @keyup.enter="parseReview(true)"
    >
      <template #append>
        <el-button :icon="Search" :loading="loading" @click="parseReview(true)" />
      </template>
    </el-input>
    <el-alert
      v-if="showDetails && errorMessage"
      :title="errorMessage"
      type="error"
      show-icon
      :closable="false"
      style="margin-top: 12px;"
    />
    <div v-if="showDetails && result" v-loading="loading" style="margin-top: 12px;">
      <div class="metric-row review-metric-row">
        <div class="metric review-metric review-metric-high">
          <div class="metric-value">{{ result.high_count }}</div>
          <div class="metric-label">High</div>
        </div>
        <div class="metric review-metric review-metric-medium">
          <div class="metric-value">{{ result.medium_count }}</div>
          <div class="metric-label">Medium</div>
        </div>
        <div class="metric review-metric review-metric-low">
          <div class="metric-value">{{ result.low_count }}</div>
          <div class="metric-label">Low</div>
        </div>
      </div>
      <el-table :data="result.items" size="small" style="margin-top: 12px;">
        <el-table-column label="级别" width="110">
          <template #default="{ row }">
            {{ severityText(row.severity) }}
          </template>
        </el-table-column>
        <el-table-column prop="title" label="Item" min-width="220" />
        <el-table-column label="状态" width="130">
          <template #default="{ row }">
            {{ issueStatusText(row.status) }}
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>
