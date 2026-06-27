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
  | 'FINALIZE_REQUESTED'
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
  mode: 'secretary' | 'coordinator'
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
  worker_key: 'codex' | 'claude' | 'gemini' | string
  name: string
  role: string
  provider_type: string
  status: 'ONLINE' | 'RUNNING' | 'FAILED' | 'OFFLINE'
  last_heartbeat_at: string | null
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

export type WorkflowActivityState =
  | 'WAITING_FOR_USER'
  | 'WAITING_FOR_HUMAN_GATE'
  | 'AGENT_RUNNING'
  | 'AGENT_SUCCEEDED'
  | 'AGENT_FAILED'
  | 'COMPLETED'

export interface WorkflowActivity {
  state: WorkflowActivityState
  message: string
  agent_run_type: string | null
  run_status: AgentRun['status'] | null
  run_id: number | null
}

export interface WorkflowActionEvidence {
  required_run_type: string
  latest_run_status: AgentRun['status'] | null
  latest_run_id: number | null
  satisfied: boolean
}

export interface WorkflowAction {
  action_id: string
  label: string
  from_status: TaskStatus
  to_status: TaskStatus
  enabled: boolean
  recommended: boolean
  requires_human_gate: boolean
  agent_run_type: string | null
  agent_run_timing: 'before_transition' | 'after_transition' | null
  instruction: string
  side_effects: string[]
  blocked_reason: string | null
  evidence: WorkflowActionEvidence | null
}

export interface WorkflowState {
  task_id: number
  current_status: TaskStatus
  activity: WorkflowActivity
  actions: WorkflowAction[]
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

export interface CoordinatorDecision {
  decision: 'continue' | 'stop'
  selected_action_id: string | null
  confidence: 'high' | 'medium' | 'low'
  reason: string
  risk_notes: string[]
}

export interface CoordinatorStepResult {
  ok: boolean
  executed: boolean
  decision: CoordinatorDecision
  action_id: string | null
  action_label: string | null
  task_status_before: TaskStatus
  task_status_after: TaskStatus
  agent_run_id: number | null
  agent_run_status: AgentRun['status'] | null
  stop_reason: string | null
  validation_errors: string[]
}

export interface CoordinatorRunResult {
  ok: boolean
  executed_steps: number
  stopped: boolean
  stop_reason: string | null
  steps: CoordinatorStepResult[]
}
