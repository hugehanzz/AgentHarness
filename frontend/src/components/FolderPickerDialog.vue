<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowUp, Folder, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '../api/client'

interface FilesystemEntry {
  name: string
  path: string
  type: 'directory'
}

const props = defineProps<{
  modelValue: boolean
  initialPath?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  select: [path: string]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const currentPath = ref('')
const parentPath = ref<string | null>(null)
const entries = ref<FilesystemEntry[]>([])
const roots = ref<FilesystemEntry[]>([])
const loading = ref(false)
const selectedPath = ref('')

async function loadRoots() {
  loading.value = true
  try {
    const { data } = await api.get<{ roots: FilesystemEntry[] }>('/filesystem/roots')
    roots.value = data.roots
    entries.value = data.roots
    currentPath.value = 'Computer'
    parentPath.value = null
  } finally {
    loading.value = false
  }
}

async function loadPath(path: string) {
  loading.value = true
  try {
    const { data } = await api.get<{ path: string; parent_path: string | null; entries: FilesystemEntry[] }>(
      '/filesystem/list',
      { params: { path } },
    )
    currentPath.value = data.path
    parentPath.value = data.parent_path
    entries.value = data.entries
    selectedPath.value = data.path
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : 'Cannot open folder')
  } finally {
    loading.value = false
  }
}

function goUp() {
  if (parentPath.value) {
    loadPath(parentPath.value)
    return
  }
  if (currentPath.value !== 'Computer') {
    loadRoots()
  }
}

function openEntry(entry: FilesystemEntry) {
  loadPath(entry.path)
}

function confirmSelection() {
  if (!selectedPath.value || selectedPath.value === 'Computer') return
  emit('select', selectedPath.value)
  visible.value = false
}

watch(
  () => props.modelValue,
  (next) => {
    if (!next) return
    if (props.initialPath) {
      loadPath(props.initialPath)
    } else {
      loadRoots()
    }
  },
)
</script>

<template>
  <el-dialog v-model="visible" title="Select Workspace Folder" width="680px">
    <div class="folder-picker">
      <div class="folder-toolbar">
        <el-button :icon="ArrowUp" :disabled="currentPath === 'Computer'" @click="goUp">Up</el-button>
        <el-button :icon="Refresh" @click="currentPath === 'Computer' ? loadRoots() : loadPath(currentPath)">Refresh</el-button>
        <div class="folder-current">{{ currentPath }}</div>
      </div>

      <div v-loading="loading" class="folder-list">
        <button
          v-for="entry in entries"
          :key="entry.path"
          class="folder-row"
          type="button"
          @click="selectedPath = entry.path"
          @dblclick="openEntry(entry)"
        >
          <el-icon><Folder /></el-icon>
          <span>{{ entry.name }}</span>
          <small>{{ entry.path }}</small>
        </button>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">Cancel</el-button>
      <el-button type="primary" :disabled="!selectedPath || selectedPath === 'Computer'" @click="confirmSelection">
        Use This Folder
      </el-button>
    </template>
  </el-dialog>
</template>
