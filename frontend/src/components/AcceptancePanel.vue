<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { api } from '../api/client'

const props = defineProps<{ taskId: number }>()

const items = ref<any[]>([])
const title = ref('')

async function load() {
  const { data } = await api.get(`/tasks/${props.taskId}/acceptance`)
  items.value = data
}

async function addItem() {
  if (!title.value.trim()) return
  await api.post(`/tasks/${props.taskId}/acceptance`, { title: title.value })
  title.value = ''
  await load()
}

onMounted(load)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <div>
        <h2 class="panel-title">Acceptance</h2>
        <div class="panel-kicker">Evidence remains confirmed by the Human Supervisor</div>
      </div>
    </div>
    <el-input v-model="title" placeholder="Acceptance item">
      <template #append>
        <el-button :icon="Plus" @click="addItem" />
      </template>
    </el-input>
    <el-table :data="items" size="small" style="margin-top: 12px;">
      <el-table-column prop="title" label="Item" min-width="220" />
      <el-table-column prop="status" label="Status" width="120" />
      <el-table-column prop="evidence" label="Evidence" min-width="180" />
    </el-table>
  </div>
</template>
