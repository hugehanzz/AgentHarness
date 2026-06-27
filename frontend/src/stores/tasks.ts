import { defineStore } from 'pinia'
import { api } from '../api/client'
import type { Task, TaskEvent, TaskStatus, Worker, WorkflowState } from '../api/types'

const workerPollIntervalMs = 5000
let workerPollTimer: ReturnType<typeof window.setInterval> | null = null

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
      // 在加载新任务之前清除过时的详情状态，以便面板不会短暂地在新路由下渲染之前的任务。
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
    async refreshTask(id: number) {
      const [{ data: detail }, { data: workflow }] = await Promise.all([
        api.get<{ task: Task; events: TaskEvent[] }>(`/tasks/${id}`),
        api.get<WorkflowState>(`/tasks/${id}/workflow`),
      ])
      this.selectedTask = detail.task
      this.events = detail.events
      this.workflow = workflow
      this.detailError = null
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
      // 刷新详情和列表视图，因为状态转换会改变当前任务行、看板计数器、分页顺序和事件。
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
    startWorkerPolling() {
      if (workerPollTimer) return
      void this.fetchWorkers().catch(() => undefined)
      workerPollTimer = window.setInterval(() => {
        void this.fetchWorkers().catch(() => undefined)
      }, workerPollIntervalMs)
    },
    stopWorkerPolling() {
      if (!workerPollTimer) return
      window.clearInterval(workerPollTimer)
      workerPollTimer = null
    },
  },
})
