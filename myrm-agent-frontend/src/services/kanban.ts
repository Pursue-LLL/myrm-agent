import { apiRequest } from '@/lib/api';

// ==================== Types ====================

export type TaskStatus = 'triage' | 'backlog' | 'ready' | 'running' | 'blocked' | 'completed' | 'failed' | 'archived';
export type TaskPriority = 'low' | 'normal' | 'high' | 'urgent';
export type BlockKind = 'human' | 'scheduled' | 'external';

export interface BoardSettings {
  max_concurrent_tasks: number;
  heartbeat_interval_seconds: number;
  zombie_timeout_seconds: number;
  max_retries_per_task: number;
  auto_block_after_consecutive_failures: number;
  specify_max_tokens: number;
  auto_specify_on_create: boolean;
  default_workdir?: string | null;
}

export interface KanbanBoard {
  board_id: string;
  name: string;
  description: string;
  settings: BoardSettings;
  created_at: string;
  updated_at: string;
}

export interface DiagnosticSummary {
  count: number;
  max_severity: 'warning' | 'error' | 'critical' | null;
}

export interface DiagnosticAction {
  kind: string;
  label: string;
  payload: Record<string, string>;
  suggested: boolean;
}

export interface TaskDiagnostic {
  rule_id: string;
  severity: 'warning' | 'error' | 'critical';
  title: string;
  detail: string;
  actions: DiagnosticAction[];
}

export interface AttachmentInfo {
  file_id: string;
  filename: string;
  content_type: string;
  url: string;
}

export interface KanbanTask {
  task_id: string;
  board_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  agent_id?: string | null;
  goal_id?: string | null;
  parent_task_id?: string | null;
  workspace_path?: string | null;
  branch?: string | null;
  retry_count: number;
  max_retries: number;
  consecutive_failures: number;
  blocked_reason?: string | null;
  block_kind?: BlockKind | null;
  scheduled_until?: string | null;
  progress_note?: string | null;
  result: string;
  error: string;
  metadata: Record<string, unknown>;
  extra_skill_ids: string[];
  attachment_ids: string[];
  attachments: AttachmentInfo[];
  max_runtime_seconds?: number | null;
  completion_criteria?: string | null;
  dep_count: number;
  children_total: number;
  children_done: number;
  comment_count: number;
  diagnostics_summary?: DiagnosticSummary | null;
  created_at: string;
  updated_at: string;
  completed_at?: string | null;
}

export interface AgentTaskCounts {
  agent_id: string | null;
  counts: Record<string, number>;
  total: number;
}

export interface BoardSummary {
  board: KanbanBoard;
  task_counts: Record<string, number>;
  total_tasks: number;
  dispatcher_active: boolean;
  by_agent: AgentTaskCounts[];
  oldest_ready_age_seconds: number | null;
}

// ==================== Board API ====================

export async function listBoards(): Promise<{ items: KanbanBoard[]; total: number }> {
  return apiRequest('/kanban/boards');
}

export async function createBoard(data: {
  name: string;
  description?: string;
  max_concurrent_tasks?: number;
  default_workdir?: string;
}): Promise<KanbanBoard> {
  return apiRequest('/kanban/boards', { method: 'POST', body: JSON.stringify(data) });
}

export async function getBoard(boardId: string): Promise<KanbanBoard> {
  return apiRequest(`/kanban/boards/${boardId}`);
}

export async function updateBoard(
  boardId: string,
  data: { name?: string; description?: string; max_concurrent_tasks?: number; default_workdir?: string | null },
): Promise<KanbanBoard> {
  return apiRequest(`/kanban/boards/${boardId}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export async function deleteBoard(boardId: string): Promise<void> {
  return apiRequest(`/kanban/boards/${boardId}`, { method: 'DELETE' });
}

export async function getBoardSummary(boardId: string): Promise<BoardSummary> {
  return apiRequest(`/kanban/boards/${boardId}/summary`);
}

// ==================== Task API ====================

export async function listTasks(
  boardId: string,
  opts?: { status?: TaskStatus; agent_id?: string; limit?: number; offset?: number },
): Promise<{ items: KanbanTask[]; total: number }> {
  const params = new URLSearchParams();
  if (opts?.status) params.set('status_filter', opts.status);
  if (opts?.agent_id) params.set('agent_id', opts.agent_id);
  if (opts?.limit) params.set('limit', String(opts.limit));
  if (opts?.offset) params.set('offset', String(opts.offset));
  const qs = params.toString();
  return apiRequest(`/kanban/boards/${boardId}/tasks${qs ? `?${qs}` : ''}`);
}

export async function createTask(
  boardId: string,
  data: {
    title: string;
    description?: string;
    priority?: TaskPriority;
    agent_id?: string;
    max_retries?: number;
    depends_on?: string[];
    extra_skill_ids?: string[];
    attachment_ids?: string[];
    completion_criteria?: string;
    max_runtime_seconds?: number;
    initial_status?: TaskStatus;
    workspace_path?: string;
    branch?: string;
  },
): Promise<KanbanTask> {
  return apiRequest(`/kanban/boards/${boardId}/tasks`, { method: 'POST', body: JSON.stringify(data) });
}

export async function getTask(taskId: string): Promise<KanbanTask> {
  return apiRequest(`/kanban/tasks/${taskId}`);
}

export async function updateTask(
  taskId: string,
  data: {
    title?: string;
    description?: string;
    priority?: TaskPriority;
    agent_id?: string | null;
    extra_skill_ids?: string[];
    attachment_ids?: string[];
    max_runtime_seconds?: number | null;
    completion_criteria?: string | null;
    result?: string;
    metadata?: Record<string, unknown>;
  },
): Promise<KanbanTask> {
  return apiRequest(`/kanban/tasks/${taskId}`, { method: 'PATCH', body: JSON.stringify(data) });
}

export async function moveTask(
  taskId: string,
  status: TaskStatus,
  opts?: { force?: boolean; block_kind?: BlockKind; blocked_reason?: string; scheduled_until?: string; result?: string; metadata?: Record<string, unknown> },
): Promise<KanbanTask> {
  const { force = false, ...rest } = opts ?? {};
  return apiRequest(`/kanban/tasks/${taskId}/move`, {
    method: 'POST',
    body: JSON.stringify({ status, force, ...rest }),
  });
}

export interface PromoteResult {
  promoted: boolean;
  forced: boolean;
  reason: string | null;
  unmet_parents: { task_id: string; title: string; status: string }[];
}

export async function promoteTask(taskId: string, force = false, reason?: string): Promise<PromoteResult> {
  return apiRequest(`/kanban/tasks/${taskId}/promote`, {
    method: 'POST',
    body: JSON.stringify({ force, reason: reason ?? null }),
  });
}

export interface ReclaimResult {
  reclaimed: boolean;
  task: KanbanTask | null;
}

export async function reclaimTask(taskId: string, reason?: string, newAgentId?: string): Promise<ReclaimResult> {
  return apiRequest(`/kanban/tasks/${taskId}/reclaim`, {
    method: 'POST',
    body: JSON.stringify({
      reason: reason ?? null,
      new_agent_id: newAgentId ?? null,
    }),
  });
}

export async function deleteTask(taskId: string): Promise<void> {
  return apiRequest(`/kanban/tasks/${taskId}`, { method: 'DELETE' });
}

// ==================== Bulk Actions ====================

export type BulkAction = 'move' | 'archive' | 'reassign' | 'reclaim' | 'delete';

export interface BulkActionResult {
  results: { task_id: string; success: boolean; error?: string }[];
  total: number;
  succeeded: number;
  failed: number;
}

export async function bulkAction(
  boardId: string,
  taskIds: string[],
  action: BulkAction,
  params: Record<string, string> = {},
  confirm = false,
): Promise<BulkActionResult> {
  return apiRequest(`/kanban/boards/${boardId}/tasks/bulk-action`, {
    method: 'POST',
    body: JSON.stringify({ task_ids: taskIds, action, params, confirm }),
  });
}

// ==================== Run & Event Types ====================

export interface TaskRun {
  run_id: string;
  task_id: string;
  worker_id: string;
  started_at: string;
  ended_at?: string | null;
  outcome?: string | null;
  summary: string;
  error: string;
  duration_seconds?: number | null;
}

export interface TaskEvent {
  event_id: number;
  task_id: string;
  kind: string;
  payload?: Record<string, unknown> | null;
  run_id?: string | null;
  created_at: string;
}

// ==================== Run & Event API ====================

export async function listRuns(taskId: string): Promise<{ items: TaskRun[]; total: number }> {
  return apiRequest(`/kanban/tasks/${taskId}/runs`);
}

export async function listEvents(
  taskId: string,
  opts?: { sinceId?: number },
): Promise<{ items: TaskEvent[]; total: number }> {
  const params = new URLSearchParams();
  if (opts?.sinceId != null) params.set('since_id', String(opts.sinceId));
  const qs = params.toString();
  return apiRequest(`/kanban/tasks/${taskId}/events${qs ? `?${qs}` : ''}`);
}

// ==================== Board Events API ====================

export interface BoardEvent {
  event_id: number;
  task_id: string;
  task_title: string;
  task_assignee: string;
  kind: string;
  payload?: Record<string, unknown> | null;
  run_id?: string | null;
  created_at: string;
}

export async function listBoardEvents(
  boardId: string,
  opts?: {
    kinds?: string[];
    assignee?: string;
    sinceId?: number;
    sinceTime?: string;
    limit?: number;
  },
): Promise<{ items: BoardEvent[]; total: number }> {
  const params = new URLSearchParams();
  if (opts?.kinds?.length) params.set('kinds', opts.kinds.join(','));
  if (opts?.assignee) params.set('assignee', opts.assignee);
  if (opts?.sinceId != null) params.set('since_id', String(opts.sinceId));
  if (opts?.sinceTime) params.set('since_time', opts.sinceTime);
  if (opts?.limit != null) params.set('limit', String(opts.limit));
  const qs = params.toString();
  return apiRequest(`/kanban/boards/${boardId}/events${qs ? `?${qs}` : ''}`);
}

// ==================== Comment API ====================

export async function addComment(taskId: string, body: string, author: string = 'user'): Promise<TaskEvent> {
  return apiRequest(`/kanban/tasks/${taskId}/comments`, {
    method: 'POST',
    body: JSON.stringify({ body, author }),
  });
}

// ==================== Dependency API ====================

export interface TaskDependency {
  parent_task_id: string;
  child_task_id: string;
}

export async function listBoardEdges(boardId: string): Promise<{ items: TaskDependency[]; total: number }> {
  return apiRequest(`/kanban/boards/${boardId}/edges`);
}

export async function listDependencies(taskId: string): Promise<{ items: string[]; total: number }> {
  return apiRequest(`/kanban/tasks/${taskId}/dependencies`);
}

export async function listDependents(taskId: string): Promise<{ items: string[]; total: number }> {
  return apiRequest(`/kanban/tasks/${taskId}/dependents`);
}

export async function addDependency(childTaskId: string, parentTaskId: string): Promise<TaskDependency> {
  return apiRequest(`/kanban/tasks/${childTaskId}/dependencies`, {
    method: 'POST',
    body: JSON.stringify({ parent_task_id: parentTaskId }),
  });
}

export async function removeDependency(childTaskId: string, parentTaskId: string): Promise<void> {
  return apiRequest(`/kanban/tasks/${childTaskId}/dependencies/${parentTaskId}`, {
    method: 'DELETE',
  });
}

// ==================== Diagnostics API ====================

export async function getTaskDiagnostics(taskId: string): Promise<{ task_id: string; diagnostics: TaskDiagnostic[] }> {
  return apiRequest(`/kanban/tasks/${taskId}/diagnostics`);
}

// ==================== Specify (TRIAGE → spec rewrite) ====================

export interface SpecifyOutcome {
  task_id: string;
  ok: boolean;
  reason: string;
  new_title: string | null;
  new_body: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  persisted: boolean;
}

export interface SpecifyAllResult {
  items: SpecifyOutcome[];
  total: number;
  persisted: boolean;
}

export async function specifyTask(taskId: string, opts?: { dryRun?: boolean }): Promise<SpecifyOutcome> {
  const dryRun = opts?.dryRun ?? true;
  return apiRequest(`/kanban/tasks/${taskId}/specify?dry_run=${dryRun}`, {
    method: 'POST',
  });
}

export async function applySpec(
  taskId: string,
  data: {
    new_title: string | null;
    new_body: string;
    prompt_tokens?: number | null;
    completion_tokens?: number | null;
  },
): Promise<SpecifyOutcome> {
  return apiRequest(`/kanban/tasks/${taskId}/apply-spec`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function specifyAllTriage(boardId: string, opts?: { dryRun?: boolean }): Promise<SpecifyAllResult> {
  const dryRun = opts?.dryRun ?? true;
  return apiRequest(`/kanban/boards/${boardId}/specify-all?dry_run=${dryRun}`, {
    method: 'POST',
  });
}

// ==================== Decompose (TRIAGE → child task graph) ====================

export interface DecomposeChildSpec {
  title: string;
  body: string;
  assignee: string | null;
  parent_indices: number[];
  extra_skill_ids: string[];
}

export interface DecomposeOutcome {
  task_id: string;
  ok: boolean;
  fanout: boolean;
  children: DecomposeChildSpec[];
  rationale: string;
  reason: string;
  new_title: string | null;
  new_body: string | null;
  new_assignee: string | null;
  child_ids: string[];
  prompt_tokens: number | null;
  completion_tokens: number | null;
  persisted: boolean;
}

export async function decomposeTask(taskId: string): Promise<DecomposeOutcome> {
  return apiRequest(`/kanban/tasks/${taskId}/decompose`, { method: 'POST' });
}

export async function applyDecompose(
  taskId: string,
  data: {
    fanout?: boolean;
    children?: DecomposeChildSpec[];
    new_title?: string | null;
    new_body?: string | null;
    new_assignee?: string | null;
    rationale?: string;
    prompt_tokens?: number | null;
    completion_tokens?: number | null;
  },
): Promise<DecomposeOutcome> {
  return apiRequest(`/kanban/tasks/${taskId}/apply-decompose`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

// ==================== Pipeline Templates API ====================

export interface PipelineQuestion {
  id: string;
  type: string;
  label: string;
  options: string[];
}

export interface PipelineQuestionGroup {
  group: string;
  group_label: string;
  questions: PipelineQuestion[];
}

export interface PipelineRole {
  role_id: string;
  description: string;
  required_skills: string[];
}

export interface PipelineTaskSeed {
  title_template: string;
  description_template: string;
  role: string;
  parents: number[];
}

export interface PipelineTemplate {
  skill_id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  task_count: number;
  roles: string[];
}

export interface PipelineTaskGraphVariant {
  id: string;
  label: string;
  description: string;
  seeds: PipelineTaskSeed[];
}

export interface PipelineTemplateDetail {
  skill_id: string;
  name: string;
  description: string;
  category: string;
  tags: string[];
  discovery_questions: PipelineQuestionGroup[];
  role_templates: PipelineRole[];
  task_graph_seed: PipelineTaskSeed[];
  task_graph_variants?: PipelineTaskGraphVariant[];
}

export interface PipelineInstantiateResult {
  task_ids: string[];
  edges: string[][];
  role_agent_mapping: Record<string, string | null>;
}

export async function listPipelines(): Promise<{ items: PipelineTemplate[]; total: number }> {
  return apiRequest('/kanban/pipelines');
}

export async function getPipelineDetail(skillId: string): Promise<PipelineTemplateDetail> {
  return apiRequest(`/kanban/pipelines/${skillId}`);
}

export async function instantiatePipeline(
  boardId: string,
  data: { skill_id: string; answers: Record<string, string>; variant_id?: string },
): Promise<PipelineInstantiateResult> {
  return apiRequest(`/kanban/boards/${boardId}/pipeline/instantiate`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}
