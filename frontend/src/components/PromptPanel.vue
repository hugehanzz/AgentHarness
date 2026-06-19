<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, Close, Edit, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'
import type { TaskStatus } from '../api/types'

const props = defineProps<{
  taskId: number
  currentStatus: TaskStatus
  taskUpdatedAt: string
  currentRunPromptType: string | null
}>()

const emit = defineEmits<{
  promptChanged: [payload: { promptType: string; content: string; matchesCurrentRun: boolean }]
}>()

const promptTypes = [
  { value: 'CODEX_PLAN', label: 'Codex：生成计划' },
  { value: 'CODEX_IMPLEMENT', label: 'Codex：实现开发' },
  { value: 'CLAUDE_REVIEW', label: 'Claude：代码评审' },
  { value: 'CODEX_FIX', label: 'Codex：修复评审问题' },
  { value: 'CLAUDE_RECHECK', label: 'Claude：复审修复结果' },
  { value: 'ACCEPTANCE_CHECKLIST', label: 'Codex：生成验收清单' },
  { value: 'README_ARCHIVE', label: 'Codex：归档' },
]

const selectedType = ref('CODEX_PLAN')
const content = ref('')
const promptDraft = ref('')
const lastLoadedContent = ref('')
const promptEditing = ref(false)
const loading = ref(false)

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
const matchesCurrentRun = computed(() => !props.currentRunPromptType || selectedType.value === props.currentRunPromptType)
const hasPromptEdits = computed(() => content.value !== lastLoadedContent.value)
const promptChanged = computed(() => promptDraft.value !== content.value)

async function loadPromptPreview() {
  loading.value = true
  try {
    const { data } = await api.get(`/tasks/${props.taskId}/prompts/preview`, {
      params: { prompt_type: selectedType.value },
    })
    content.value = data.content
    promptDraft.value = data.content
    lastLoadedContent.value = data.content
    promptEditing.value = false
  } finally {
    loading.value = false
  }
}

async function refreshPromptPreview() {
  try {
    await loadPromptPreview()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || error?.message || 'Prompt preview failed')
  }
}

function emitPromptChanged() {
  emit('promptChanged', {
    promptType: selectedType.value,
    content: content.value,
    matchesCurrentRun: matchesCurrentRun.value,
  })
}

function startPromptEdit() {
  promptDraft.value = content.value
  promptEditing.value = true
}

function cancelPromptEdit() {
  promptDraft.value = content.value
  promptEditing.value = false
}

function savePromptEdit() {
  content.value = promptDraft.value
  promptEditing.value = false
}

watch(
  () => props.currentStatus,
  () => {
    selectedType.value = recommendedType.value
  },
  { immediate: true },
)

watch(
  [selectedType, () => props.taskUpdatedAt],
  () => {
    refreshPromptPreview()
  },
  { immediate: true },
)

watch(
  [selectedType, content, matchesCurrentRun],
  () => {
    emitPromptChanged()
  },
  { immediate: true },
)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div>
        <h2 class="panel-title">Agent Prompt</h2>
      </div>
      <el-button
        v-if="!promptEditing"
        class="icon-button"
        :icon="Edit"
        :disabled="!matchesCurrentRun || !content || loading"
        @click="startPromptEdit"
      >
        Edit
      </el-button>
    </div>
    <div class="copy-row">
      <el-select v-model="selectedType" :disabled="promptEditing" style="width: 240px">
        <el-option v-for="item in promptTypes" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-tag v-if="hasPromptEdits" type="warning" effect="plain">Edited</el-tag>
      <el-tag v-if="!matchesCurrentRun" type="info" effect="plain">Preview only</el-tag>
      <el-button
        class="icon-button"
        :icon="Refresh"
        :loading="loading"
        :disabled="promptEditing"
        circle
        @click="refreshPromptPreview"
      />
    </div>
    <div v-if="content && !promptEditing" v-loading="loading" class="prompt-box" style="margin-top: 12px;">{{ content }}</div>
    <el-input
      v-if="content && promptEditing"
      v-model="promptDraft"
      v-loading="loading"
      class="prompt-editor"
      type="textarea"
      :rows="16"
      resize="vertical"
      spellcheck="false"
      style="margin-top: 12px;"
    />
    <div v-if="promptEditing" class="copy-row" style="margin-top: 12px;">
      <el-button :icon="Close" @click="cancelPromptEdit">Cancel</el-button>
      <el-button type="primary" :icon="Check" :disabled="!promptChanged" @click="savePromptEdit">Save</el-button>
    </div>
  </div>
</template>

<style scoped>
.prompt-editor :deep(.el-textarea__inner) {
  min-height: 360px;
  border-radius: 6px;
  background: #f9fbfd;
  color: #1f2937;
  font-family: Consolas, 'SFMono-Regular', Menlo, monospace;
  font-size: 12px;
  line-height: 1.65;
}
</style>
