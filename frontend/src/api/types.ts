export type TaskStatus =
  | 'REQUIREMENT_DRAFT'
  | 'PLAN_REQUESTED'
  | 'PLAN_READY'
  | 'PLAN_CONFIRMED'
  | 'IMPLEMENTING'
  | 'IMPLEMENT_DONE'
  | 'REVIEW_REQUESTED'
  | 'REVIEW_DONE'
  | 'FIX_REQUIRED'
  | 'FIXING'
  | 'FIX_DONE'
  | 'RECHECK_REQUESTED'
  | 'RECHECK_DONE'
  | 'ACCEPTANCE_READY'
  | 'ACCEPTANCE_PASSED'
  | 'ARCHIVED'
  | 'DONE'

export interface Task {
  id: number
  title: string
  description: string
  workspace_path: string | null
  status: TaskStatus
  priority: 'LOW' | 'MEDIUM' | 'HIGH'
  created_at: string
  updated_at: string
  archived_at: string | null
}

export interface TaskEvent {
  id: number
  task_id: number
  event_type: string
  from_status: TaskStatus | null
  to_status: TaskStatus | null
  message: string | null
  created_by: string
  created_at: string
}

export interface Worker {
  id: number
  name: string
  role: string
  worker_type: string
  status: string
  last_heartbeat_at: string | null
  current_task_id: number | null
  is_online: boolean
}

export interface AgentRun {
  id: number
  task_id: number | null
  worker_id: number | null
  agent_session_id: number | null
  run_type: string
  provider_type: string
  external_thread_id: string | null
  external_turn_id: string | null
  command_display: string | null
  cwd: string | null
  exit_code: number | null
  status: 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'TIMED_OUT'
  input_payload: string | null
  output_payload: string | null
  stderr: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
}

export interface GeminiGateFact {
  type: string
  owner: string
  reason: string
  blocks_auto_advance: boolean
}

export interface GeminiTaskBrief {
  ok: boolean
  model: string
  facts_version: string
  summary: string
  current_position: string
  pending_gate: GeminiGateFact | null
  suggested_next_steps: string[]
  risk_notes: string[]
}

export interface GeminiTaskFacts {
  facts_version: string
}
