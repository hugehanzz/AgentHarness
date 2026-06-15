<script setup lang="ts">
import { ref } from 'vue'
import { CopyDocument, MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

const props = defineProps<{ taskId: number }>()

const promptTypes = [
  'CODEX_PLAN',
  'CODEX_IMPLEMENT',
  'CLAUDE_REVIEW',
  'CODEX_FIX',
  'CLAUDE_RECHECK',
  'ACCEPTANCE_CHECKLIST',
  'README_ARCHIVE',
]

const selectedType = ref('CODEX_PLAN')
const content = ref('')

async function generatePrompt() {
  const { data } = await api.post(`/tasks/${props.taskId}/prompts`, { prompt_type: selectedType.value })
  content.value = data.content
}

async function copyPrompt() {
  await navigator.clipboard.writeText(content.value)
  ElMessage.success('Copied')
}
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div>
        <h2 class="panel-title">Prompt Builder</h2>
        <div class="panel-kicker">Generate handoff prompts for Codex and Claude-DeepSeek</div>
      </div>
    </div>
    <div class="copy-row">
      <el-select v-model="selectedType" style="width: 240px">
        <el-option v-for="item in promptTypes" :key="item" :label="item" :value="item" />
      </el-select>
      <el-button type="primary" :icon="MagicStick" @click="generatePrompt">Generate</el-button>
      <el-button :icon="CopyDocument" :disabled="!content" @click="copyPrompt">Copy</el-button>
    </div>
    <div v-if="content" class="prompt-box" style="margin-top: 12px;">{{ content }}</div>
  </div>
</template>
