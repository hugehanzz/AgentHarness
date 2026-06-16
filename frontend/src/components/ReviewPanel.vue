<script setup lang="ts">
import { ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { api } from '../api/client'

const props = defineProps<{ taskId: number; workspacePath: string | null }>()

const workspacePath = ref(props.workspacePath || '')
const result = ref<any | null>(null)

function recheckClass(status: string) {
  return `recheck-${status || 'UNKNOWN'}`
}

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

async function parseReview() {
  const { data } = await api.post('/reviews/parse', {
    workspace_path: workspacePath.value,
    task_id: props.taskId,
  })
  result.value = data
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div>
        <h2 class="panel-title">Review Results</h2>
      </div>
    </div>
    <el-input v-model="workspacePath" placeholder="Workspace path">
      <template #append>
        <el-button :icon="Search" @click="parseReview" />
      </template>
    </el-input>
    <div v-if="result" style="margin-top: 12px;">
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
          <div class="review-metric-footer">
            <span class="metric-label">Low</span>
            <span :class="['recheck-pill', recheckClass(result.recheck_status)]">{{ result.recheck_status }}</span>
          </div>
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
