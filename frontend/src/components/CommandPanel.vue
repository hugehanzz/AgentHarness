<script setup lang="ts">
import { ref } from 'vue'
import { Operation } from '@element-plus/icons-vue'
import { api } from '../api/client'

const props = defineProps<{ taskId: number; workspacePath: string | null }>()

const workspacePath = ref(props.workspacePath || '')
const result = ref<any | null>(null)

async function run(commandKey: string) {
  const { data } = await api.post('/commands/run', {
    command_key: commandKey,
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
        <h2 class="panel-title">Safe Commands</h2>
        <div class="panel-kicker">Whitelist execution only, no arbitrary shell input</div>
      </div>
    </div>
    <el-input v-model="workspacePath" placeholder="Workspace path" style="margin-bottom: 12px;" />
    <el-space wrap>
      <el-button :icon="Operation" @click="run('git_status')">git status</el-button>
      <el-button :icon="Operation" @click="run('git_diff_stat')">git diff --stat</el-button>
    </el-space>
    <div v-if="result" style="margin-top: 12px;">
      <el-tag :type="result.status === 'SUCCEEDED' ? 'success' : 'danger'">{{ result.status }}</el-tag>
      <span class="muted" style="margin-left: 8px;">exit {{ result.exit_code }} · {{ result.duration_ms }}ms</span>
      <div class="output-box" style="margin-top: 8px;">{{ result.stdout || result.stderr }}</div>
    </div>
  </div>
</template>
