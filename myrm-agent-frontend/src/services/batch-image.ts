import { apiRequest } from '@/lib/api';

export interface BatchPlanItem {
  index: number;
  prompt: string;
  model: string | null;
  size: string | null;
  quality: string | null;
  status: string;
  error: string | null;
  media_id: string | null;
}

export interface BatchJob {
  id: string;
  status: string;
  total_items: number;
  completed_items: number;
  failed_items: number;
  plan: BatchPlanItem[] | null;
  concurrency: number;
  estimated_cost: string | null;
  session_id: string | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface CreateBatchJobRequest {
  items: { prompt: string; model?: string; size?: string; quality?: string }[];
  concurrency?: number;
  session_id?: string;
}

export async function createBatchJob(req: CreateBatchJobRequest): Promise<BatchJob> {
  return apiRequest<BatchJob>('/media/batch', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

export async function startBatchJob(jobId: string): Promise<BatchJob> {
  return apiRequest<BatchJob>(`/media/batch/${jobId}/start`, { method: 'POST' });
}

export async function pauseBatchJob(jobId: string): Promise<BatchJob> {
  return apiRequest<BatchJob>(`/media/batch/${jobId}/pause`, { method: 'POST' });
}

export async function resumeBatchJob(jobId: string): Promise<BatchJob> {
  return apiRequest<BatchJob>(`/media/batch/${jobId}/resume`, { method: 'POST' });
}

export async function cancelBatchJob(jobId: string): Promise<BatchJob> {
  return apiRequest<BatchJob>(`/media/batch/${jobId}/cancel`, { method: 'POST' });
}

export async function retryFailedItems(jobId: string): Promise<BatchJob> {
  return apiRequest<BatchJob>(`/media/batch/${jobId}/retry`, { method: 'POST' });
}

export async function getBatchJob(jobId: string): Promise<BatchJob> {
  return apiRequest<BatchJob>(`/media/batch/${jobId}`);
}
