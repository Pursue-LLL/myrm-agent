/**
 * BatchDirectory API service — same prompt × N directories parallel runs.
 *
 * [INPUT]
 * - @/lib/api::apiRequest (POS: HTTP API 封装)
 *
 * [OUTPUT]
 * - listBatchProjects / getBatchProject / createBatchProject / cancelBatchProject / deleteBatchProject
 *
 * [POS]
 * BatchDirectory 前端 API 服务层。封装批量目录并行项目的增删查与取消。
 */

import { apiRequest } from '@/lib/api';

export type BatchProjectStatus = 'draft' | 'running' | 'completed' | 'failed' | 'cancelled';

export interface BatchTaskItem {
  task_id: string;
  title: string;
  status: string;
  workspace_path: string | null;
  agent_id: string | null;
  result: string;
  error: string;
  artifact_status?: 'verified' | 'missing' | 'not_specified';
  created_at: string | null;
  completed_at: string | null;
}

export interface BatchProject {
  project_id: string;
  name: string;
  prompt: string;
  board_id: string | null;
  status: BatchProjectStatus;
  concurrency: number;
  agent_id: string | null;
  model_override: string | null;
  max_runtime_seconds: number | null;
  require_approval: boolean;
  notify_enabled: boolean;
  directories: string[];
  artifact_patterns: string[];
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  failed_directories?: string[];
  missing_artifact_directories?: string[];
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface BatchProjectDetail extends BatchProject {
  tasks: BatchTaskItem[];
  created_task_ids?: string[];
  cancelled_task_ids?: string[];
  retried_task_ids?: string[];
  retry_failed_directories?: string[];
  rerun_task_ids?: string[];
  rerun_failed_directories?: string[];
}

export interface CreateBatchProjectInput {
  name: string;
  prompt: string;
  directories: string[];
  board_id?: string | null;
  concurrency?: number;
  agent_id?: string | null;
  model_override?: string | null;
  max_runtime_seconds?: number | null;
  require_approval?: boolean;
  notify_enabled?: boolean;
  artifact_patterns?: string[];
}

export async function listBatchProjects(): Promise<BatchProject[]> {
  const data = await apiRequest<{ items: BatchProject[] }>('/batch-directories');
  return data.items ?? [];
}

export async function getBatchProject(projectId: string): Promise<BatchProjectDetail> {
  return apiRequest(`/batch-directories/${projectId}`);
}

export async function createBatchProject(input: CreateBatchProjectInput): Promise<BatchProjectDetail> {
  return apiRequest('/batch-directories', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export async function cancelBatchProject(projectId: string): Promise<BatchProjectDetail> {
  return apiRequest(`/batch-directories/${projectId}/cancel`, { method: 'POST' });
}

export async function retryBatchProject(projectId: string): Promise<BatchProjectDetail> {
  return apiRequest(`/batch-directories/${projectId}/retry`, { method: 'POST' });
}

export async function rerunBatchProject(projectId: string): Promise<BatchProjectDetail> {
  return apiRequest(`/batch-directories/${projectId}/rerun`, { method: 'POST' });
}

export async function retryBatchTask(
  projectId: string,
  taskId: string,
): Promise<BatchProjectDetail> {
  return apiRequest(`/batch-directories/${projectId}/tasks/${taskId}/retry`, { method: 'POST' });
}

export async function deleteBatchProject(projectId: string): Promise<void> {
  await apiRequest(`/batch-directories/${projectId}`, { method: 'DELETE' });
}

export function isBatchTerminalStatus(status: BatchProjectStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}
