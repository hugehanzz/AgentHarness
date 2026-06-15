import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { Task, TaskEvent, TaskStatus, Worker } from '../api/types'

interface State {
  tasks: Task[]
  selectedTask: Task | null
  events: TaskEvent[]
  workers: Worker[]
  detailLoading: boolean
  detailError: string | null
}

export const useTasksStore = defineStore('tasks', {
  state: (): State => ({
    tasks: [],
    selectedTask: null,
    events: [],
    workers: [],
    detailLoading: false,
    detailError: null,
  }),
  actions: {
    async fetchTasks() {
      const { data } = await api.get<Task[]>('/tasks')
      this.tasks = data
    },
    async fetchTask(id: number) {
      this.detailLoading = true
      this.detailError = null
      this.selectedTask = null
      this.events = []
      try {
        const { data } = await api.get<{ task: Task; events: TaskEvent[] }>(`/tasks/${id}`)
        this.selectedTask = data.task
        this.events = data.events
      } catch (error) {
        this.detailError = error instanceof Error ? error.message : 'Failed to load task detail'
        throw error
      } finally {
        this.detailLoading = false
      }
    },
    async createTask(payload: { title: string; description: string; workspace_path?: string }) {
      await api.post('/tasks', payload)
      await this.fetchTasks()
    },
    async transitionTask(id: number, toStatus: TaskStatus, message?: string) {
      await api.post(`/tasks/${id}/transition`, { to_status: toStatus, message })
      await this.fetchTask(id)
      await this.fetchTasks()
    },
    async fetchWorkers() {
      const { data } = await api.get<Worker[]>('/workers')
      this.workers = data
    },
  },
})
