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
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface BatchProjectDetail extends BatchProject {
  tasks: BatchTaskItem[];
  created_task_ids?: string[];
  failed_directories?: string[];
  cancelled_task_ids?: string[];
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

export async function deleteBatchProject(projectId: string): Promise<void> {
  await apiRequest(`/batch-directories/${projectId}`, { method: 'DELETE' });
}

export function isBatchTerminalStatus(status: BatchProjectStatus): boolean {
  return status === 'completed' || status === 'failed' || status === 'cancelled';
}
