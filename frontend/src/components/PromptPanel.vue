<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { CopyDocument, MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import type { TaskStatus } from '../api/types'

const props = defineProps<{ taskId: number; currentStatus: TaskStatus }>()

const promptTypes = [
  { value: 'CODEX_PLAN', label: 'Codex：生成计划' },
  { value: 'CODEX_IMPLEMENT', label: 'Codex：实现开发' },
  { value: 'CLAUDE_REVIEW', label: 'Claude：代码评审' },
  { value: 'CODEX_FIX', label: 'Codex：修复评审问题' },
  { value: 'CLAUDE_RECHECK', label: 'Claude：复审修复结果' },
  { value: 'ACCEPTANCE_CHECKLIST', label: '生成验收清单' },
  { value: 'README_ARCHIVE', label: '生成归档说明' },
]

const selectedType = ref('CODEX_PLAN')
const content = ref('')

const recommendedPromptByStatus: Record<TaskStatus, string> = {
  REQUIREMENT_DRAFT: 'CODEX_PLAN',
  PLAN_REQUESTED: 'CODEX_PLAN',
  PLAN_READY: 'CODEX_PLAN',
  PLAN_CONFIRMED: 'CODEX_IMPLEMENT',
  IMPLEMENTING: 'CODEX_IMPLEMENT',
  IMPLEMENT_DONE: 'CLAUDE_REVIEW',
  REVIEW_REQUESTED: 'CLAUDE_REVIEW',
  REVIEW_DONE: 'CODEX_FIX',
  FIX_REQUIRED: 'CODEX_FIX',
  FIXING: 'CODEX_FIX',
  FIX_DONE: 'CLAUDE_RECHECK',
  RECHECK_REQUESTED: 'CLAUDE_RECHECK',
  RECHECK_DONE: 'ACCEPTANCE_CHECKLIST',
  ACCEPTANCE_READY: 'ACCEPTANCE_CHECKLIST',
  ACCEPTANCE_PASSED: 'README_ARCHIVE',
  ARCHIVED: 'README_ARCHIVE',
  DONE: 'README_ARCHIVE',
}

const recommendedType = computed(() => recommendedPromptByStatus[props.currentStatus])

async function generatePrompt() {
  const { data } = await api.post(`/tasks/${props.taskId}/prompts`, { prompt_type: selectedType.value })
  content.value = data.content
}

async function copyPrompt() {
  await navigator.clipboard.writeText(content.value)
  ElMessage.success('Copied')
}

watch(
  () => props.currentStatus,
  () => {
    selectedType.value = recommendedType.value
  },
  { immediate: true },
)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div>
        <h2 class="panel-title">Prompt Builder</h2>
      </div>
    </div>
    <div class="copy-row">
      <el-select v-model="selectedType" style="width: 240px">
        <el-option v-for="item in promptTypes" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-button type="primary" :icon="MagicStick" @click="generatePrompt">Build Prompt</el-button>
      <el-button :icon="CopyDocument" :disabled="!content" @click="copyPrompt">Copy</el-button>
    </div>
    <div v-if="content" class="prompt-box" style="margin-top: 12px;">{{ content }}</div>
  </div>
</template>
