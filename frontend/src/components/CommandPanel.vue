<script setup lang="ts">
import { computed, ref } from 'vue'
import { Operation } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const props = defineProps<{ taskId: number; workspacePath: string | null }>()

const workspacePath = ref(props.workspacePath || '')
const result = ref<any | null>(null)
const runningCommand = ref('')
const errorMessage = ref('')

const outputText = computed(() => {
  if (!result.value) return ''
  const output = result.value.stdout || result.value.stderr || ''
  if (output.trim()) return output
  if (result.value.command_key === 'git_status' && result.value.status === 'SUCCEEDED') {
    return 'Working tree clean. No changes reported by git status --short.'
  }
  if (result.value.command_key === 'git_diff_stat' && result.value.status === 'SUCCEEDED') {
    return 'No tracked file diff reported by git diff --stat.'
  }
  return 'Command completed with no output.'
})

async function run(commandKey: string) {
  // The backend accepts only command keys, never raw shell text. This panel is a
  // thin UI over the safe-command whitelist.
  errorMessage.value = ''
  result.value = null
  runningCommand.value = commandKey
  try {
    const { data } = await api.post('/commands/run', {
      command_key: commandKey,
      workspace_path: workspacePath.value,
      task_id: props.taskId,
    })
    result.value = data
  } catch (error: any) {
    errorMessage.value = error?.response?.data?.detail || error?.message || 'Command failed'
    ElMessage.error(errorMessage.value)
  } finally {
    runningCommand.value = ''
  }
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div>
        <h2 class="panel-title">Safe Commands</h2>
      </div>
    </div>
    <el-input v-model="workspacePath" placeholder="Workspace path" style="margin-bottom: 12px;" />
    <el-space wrap>
      <el-button
        :icon="Operation"
        :loading="runningCommand === 'git_status'"
        :disabled="!workspacePath.trim() || Boolean(runningCommand)"
        @click="run('git_status')"
      >
        git status
      </el-button>
      <el-button
        :icon="Operation"
        :loading="runningCommand === 'git_diff_stat'"
        :disabled="!workspacePath.trim() || Boolean(runningCommand)"
        @click="run('git_diff_stat')"
      >
        git diff --stat
      </el-button>
    </el-space>
    <div v-if="errorMessage" class="output-box command-output command-output-error">
      {{ errorMessage }}
    </div>
    <div v-if="result" style="margin-top: 12px;">
      <el-tag :type="result.status === 'SUCCEEDED' ? 'success' : 'danger'">{{ result.status }}</el-tag>
      <div class="output-box command-output">{{ outputText }}</div>
    </div>
  </div>
</template>

<style scoped>
.command-output {
  margin-top: 8px;
  white-space: pre-wrap;
}

.command-output-error {
  border-color: #f5c2c7;
  color: #842029;
}
</style>
