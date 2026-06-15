<script setup lang="ts">
import { ref } from 'vue'
import { Search } from '@element-plus/icons-vue'
import { api } from '../api/client'

const props = defineProps<{ taskId: number; workspacePath: string | null }>()

const workspacePath = ref(props.workspacePath || '')
const result = ref<any | null>(null)

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
        <h2 class="panel-title">REVIEW.md Parser</h2>
        <div class="panel-kicker">Read-only extraction of issues and recheck conclusion</div>
      </div>
    </div>
    <el-input v-model="workspacePath" placeholder="Workspace path">
      <template #append>
        <el-button :icon="Search" @click="parseReview" />
      </template>
    </el-input>
    <div v-if="result" style="margin-top: 12px;">
      <div class="metric-row">
        <div class="metric">
          <div class="metric-value">{{ result.high_count }}</div>
          <div class="metric-label">High</div>
        </div>
        <div class="metric">
          <div class="metric-value">{{ result.medium_count }}</div>
          <div class="metric-label">Medium</div>
        </div>
        <div class="metric">
          <div class="metric-value">{{ result.low_count }}</div>
          <div class="metric-label">Low · {{ result.recheck_status }}</div>
        </div>
      </div>
      <el-table :data="result.items" size="small" style="margin-top: 12px;">
        <el-table-column prop="severity" label="Severity" width="110" />
        <el-table-column prop="title" label="Item" min-width="220" />
        <el-table-column prop="status" label="Status" width="110" />
      </el-table>
    </div>
  </div>
</template>
