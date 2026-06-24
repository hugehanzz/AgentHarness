import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { Task, TaskEvent, TaskStatus, Worker, WorkflowState } from '../api/types'

interface State {
  tasks: Task[]
  selectedTask: Task | null
  events: TaskEvent[]
  workers: Worker[]
  workflow: WorkflowState | null
  detailLoading: boolean
  detailError: string | null
}

export const useTasksStore = defineStore('tasks', {
  state: (): State => ({
    tasks: [],
    selectedTask: null,
    events: [],
    workers: [],
    workflow: null,
    detailLoading: false,
    detailError: null,
  }),
  actions: {
    async fetchTasks() {
      const { data } = await api.get<Task[]>('/tasks')
      this.tasks = data
    },
    async fetchTask(id: number) {
      // Clear stale detail state before loading a new task so panels do not
      // briefly render the previous task under the new route.
      this.detailLoading = true
      this.detailError = null
      this.selectedTask = null
      this.events = []
      this.workflow = null
      try {
        const [{ data: detail }, { data: workflow }] = await Promise.all([
          api.get<{ task: Task; events: TaskEvent[] }>(`/tasks/${id}`),
          api.get<WorkflowState>(`/tasks/${id}/workflow`),
        ])
        this.selectedTask = detail.task
        this.events = detail.events
        this.workflow = workflow
      } catch (error) {
        this.detailError = error instanceof Error ? error.message : 'Failed to load task detail'
        throw error
      } finally {
        this.detailLoading = false
      }
    },
    async fetchWorkflow(id: number) {
      const { data } = await api.get<WorkflowState>(`/tasks/${id}/workflow`)
      this.workflow = data
    },
    async createTask(payload: { title: string; description: string; workspace_path?: string; mode?: 'secretary' | 'coordinator' }) {
      await api.post('/tasks', payload)
      await this.fetchTasks()
    },
    async transitionTask(id: number, toStatus: TaskStatus, message?: string) {
      await api.post(`/tasks/${id}/transition`, { to_status: toStatus, message })
      // Refresh both detail and list views because a transition changes the
      // current task row, board counters, pagination ordering, and events.
      await this.fetchTask(id)
      await this.fetchTasks()
    },
    async updateRequirement(id: number, description: string) {
      await api.patch(`/tasks/${id}/requirement`, { description })
      await this.fetchTask(id)
      await this.fetchTasks()
    },
    async fetchWorkers() {
      const { data } = await api.get<Worker[]>('/workers')
      this.workers = data
    },
  },
})
