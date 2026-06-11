import { apiRequest } from '@/lib/api';

export interface CheckpointInfo {
  taskId: string;
  agentType: string;
  sessionId: string;
  timestamp: number;
  progress: number;
  lastTool: string | null;
  resumable: boolean;
}

export interface CheckpointListResponse {
  checkpoints: CheckpointInfo[];
  total: number;
}

export interface CheckpointResumeResponse {
  status: string;
  taskId: string;
  message: string;
  sessionId: string | null;
  messagesCount: number;
  checkpointData: Record<string, unknown> | null;
}

export interface CheckpointCleanupResponse {
  status: string;
  deleted: number;
  ttlDays: number;
}

// File Snapshot types

export interface FileSnapshotInfo {
  snapshotId: string;
  workingDir: string;
  trigger: string;
  createdAt: number;
  fileCount: number;
  description: string;
  externalEffects: string[];
}

export interface FileSnapshotListResponse {
  snapshots: FileSnapshotInfo[];
  total: number;
}

export interface FileSnapshotRestoreResponse {
  success: boolean;
  snapshotId: string;
  filesRestored: number;
  preRollbackSnapshotId: string | null;
  error: string | null;
}

export interface FileChange {
  path: string;
  changeType: string;
  oldSize: number | null;
  newSize: number | null;
  linesAdded: number | null;
  linesDeleted: number | null;
}

export interface FileDiffResponse {
  snapshotId: string;
  changes: FileChange[];
  totalChanges: number;
}

/**
 * List all saved checkpoints
 */
export const listCheckpoints = async (sessionId?: string, limit: number = 50): Promise<CheckpointListResponse> => {
  const params = new URLSearchParams();
  if (sessionId) params.append('session_id', sessionId);
  params.append('limit', limit.toString());

  const queryString = params.toString();
  const url = `/checkpoint/list${queryString ? `?${queryString}` : ''}`;

  return (await apiRequest(url)) as CheckpointListResponse;
};

/**
 * Resume from checkpoint
 */
export const resumeCheckpoint = async (taskId: string): Promise<CheckpointResumeResponse> => {
  return (await apiRequest('/checkpoint/resume', {
    method: 'POST',
    body: JSON.stringify({ taskId }),
  })) as CheckpointResumeResponse;
};

/**
 * Delete checkpoint
 */
export const deleteCheckpoint = async (taskId: string): Promise<{ status: string; taskId: string }> => {
  return (await apiRequest(`/checkpoint/${taskId}`, {
    method: 'DELETE',
  })) as { status: string; taskId: string };
};

/**
 * Cleanup old checkpoints
 */
export const cleanupCheckpoints = async (ttlDays: number = 7): Promise<CheckpointCleanupResponse> => {
  return (await apiRequest(`/checkpoint/cleanup?ttl_days=${ttlDays}`, {
    method: 'POST',
  })) as CheckpointCleanupResponse;
};

// ============================================================================
// File Snapshot API
// ============================================================================

/**
 * List file snapshots for a workspace
 */
export const listFileSnapshots = async (workingDir: string, limit: number = 20): Promise<FileSnapshotListResponse> => {
  const params = new URLSearchParams();
  params.append('working_dir', workingDir);
  params.append('limit', limit.toString());

  return (await apiRequest(`/checkpoint/file-snapshot/list?${params.toString()}`)) as FileSnapshotListResponse;
};

/**
 * Restore a file snapshot
 */
export const restoreFileSnapshot = async (
  snapshotId: string,
  files?: string[],
): Promise<FileSnapshotRestoreResponse> => {
  return (await apiRequest('/checkpoint/file-snapshot/restore', {
    method: 'POST',
    body: JSON.stringify({ snapshotId, files }),
  })) as FileSnapshotRestoreResponse;
};

/**
 * Get diff between snapshot and current state
 */
export const getFileSnapshotDiff = async (snapshotId: string): Promise<FileDiffResponse> => {
  return (await apiRequest(`/checkpoint/file-snapshot/${snapshotId}/diff`)) as FileDiffResponse;
};

/**
 * Delete a file snapshot
 */
export const deleteFileSnapshot = async (snapshotId: string): Promise<{ status: string; snapshotId: string }> => {
  return (await apiRequest(`/checkpoint/file-snapshot/${snapshotId}`, {
    method: 'DELETE',
  })) as { status: string; snapshotId: string };
};

/**
 * Cleanup old file snapshots
 */
export const cleanupFileSnapshots = async (
  workingDir: string,
  maxSnapshots: number = 20,
): Promise<{ status: string; deleted: number; maxSnapshots: number }> => {
  const params = new URLSearchParams();
  params.append('working_dir', workingDir);
  params.append('max_snapshots', maxSnapshots.toString());

  return (await apiRequest(`/checkpoint/file-snapshot/cleanup?${params.toString()}`, {
    method: 'POST',
  })) as { status: string; deleted: number; maxSnapshots: number };
};
