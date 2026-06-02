/**
 * Task types for frontend.
 */

export type TaskStatus = 'pending' | 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface TaskError {
  error_type: string;
  message: string;
  recoverable: 'transient' | 'permanent';
}

export interface Task {
  task_id: string;
  task_type: string;
  status: TaskStatus;
  payload: Record<string, unknown>;
  result?: Record<string, unknown>;
  error?: TaskError;
  priority: number;
  progress: number;
  progress_message?: string;
  created_at: string;
  updated_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface ImageGenerationResult {
  images: Array<{
    url: string;
    width?: number;
    height?: number;
    mime_type?: string;
  }>;
  model: string;
  provider: string;
  latency_ms?: number;
}
