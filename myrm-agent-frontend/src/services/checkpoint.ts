import { apiRequest } from '@/lib/api';

export interface CheckpointInfo {
  taskId: string;
  agentType: string;
  sessionId: string;
  timestamp: number;
  progress: number;
  lastTool: string | null;
  resumable: boolean;
  taskDescription: string;
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
  agentId: string | null;
}

export interface FileSnapshotListResponse {
  snapshots: FileSnapshotInfo[];
  total: number;
}

export interface FileSnapshotCreateResponse {
  success: boolean;
  snapshotId: string;
  workingDir: string;
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

// ============================================================================
// snake_case → camelCase mapping
//
// The backend serializes these endpoints with snake_case keys (task_id, agent_type,
// snapshot_id, ...) while the UI consumes camelCase. This is the single place
// that normalizes responses so components never see a field-name mismatch.
// ============================================================================

const snakeToCamelKey = (key: string): string => key.replace(/_([a-z0-9])/g, (_, ch: string) => ch.toUpperCase());

const toCamel = <T>(value: unknown, preserveValues?: ReadonlySet<string>): T => {
  if (Array.isArray(value)) {
    return value.map((item) => toCamel<unknown>(item, preserveValues)) as T;
  }
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => {
        const camelKey = snakeToCamelKey(k);
        // Pass-through values (e.g. checkpoint_data) keep their raw nested keys:
        // they are opaque payloads owned by the backend, not UI-shaped fields.
        return preserveValues?.has(k) ? [camelKey, v] : [camelKey, toCamel<unknown>(v, preserveValues)];
      }),
    ) as T;
  }
  return value as T;
};

// ============================================================================
// Subagent Checkpoint API
// ============================================================================

/**
 * List all saved checkpoints
 */
export const listCheckpoints = async (sessionId?: string, limit: number = 50): Promise<CheckpointListResponse> => {
  const params = new URLSearchParams();
  if (sessionId) {params.append('session_id', sessionId);}
  params.append('limit', limit.toString());

  const queryString = params.toString();
  const url = `/checkpoint/list${queryString ? `?${queryString}` : ''}`;

  return toCamel<CheckpointListResponse>(await apiRequest(url));
};

/**
 * Resume from checkpoint
 */
export const resumeCheckpoint = async (taskId: string): Promise<CheckpointResumeResponse> => {
  return toCamel<CheckpointResumeResponse>(
    await apiRequest('/checkpoint/resume', {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId }),
    }),
    new Set(['checkpoint_data']),
  );
};

/**
 * Delete checkpoint
 */
export const deleteCheckpoint = async (taskId: string): Promise<{ status: string; taskId: string }> => {
  return toCamel<{ status: string; taskId: string }>(await apiRequest(`/checkpoint/${taskId}`, {
    method: 'DELETE',
  }));
};

/**
 * Cleanup old checkpoints
 */
export const cleanupCheckpoints = async (ttlDays: number = 7): Promise<CheckpointCleanupResponse> => {
  return toCamel<CheckpointCleanupResponse>(await apiRequest(`/checkpoint/cleanup?ttl_days=${ttlDays}`, {
    method: 'POST',
  }));
};

// ============================================================================
// File Snapshot API
// ============================================================================

/**
 * List file snapshots for a workspace
 */
export const listFileSnapshots = async (
  workingDir: string,
  limit: number = 20,
  agentId?: string,
): Promise<FileSnapshotListResponse> => {
  const params = new URLSearchParams();
  params.append('working_dir', workingDir);
  params.append('limit', limit.toString());
  if (agentId) {params.append('agent_id', agentId);}

  return toCamel<FileSnapshotListResponse>(await apiRequest(`/checkpoint/file-snapshot/list?${params.toString()}`));
};

/**
 * Create a manual snapshot of the workspace
 */
export const createFileSnapshot = async (
  workingDir: string,
  description: string = '',
): Promise<FileSnapshotCreateResponse> => {
  return toCamel<FileSnapshotCreateResponse>(await apiRequest('/checkpoint/file-snapshot/create', {
    method: 'POST',
    body: JSON.stringify({ working_dir: workingDir, description }),
  }));
};

/**
 * Restore a file snapshot
 */
export const restoreFileSnapshot = async (
  snapshotId: string,
  files?: string[],
): Promise<FileSnapshotRestoreResponse> => {
  return toCamel<FileSnapshotRestoreResponse>(await apiRequest('/checkpoint/file-snapshot/restore', {
    method: 'POST',
    body: JSON.stringify({ snapshot_id: snapshotId, files }),
  }));
};

/**
 * Get diff between snapshot and current state
 */
export const getFileSnapshotDiff = async (snapshotId: string): Promise<FileDiffResponse> => {
  return toCamel<FileDiffResponse>(await apiRequest(`/checkpoint/file-snapshot/${snapshotId}/diff`));
};

/**
 * Delete a file snapshot
 */
export const deleteFileSnapshot = async (snapshotId: string): Promise<{ status: string; snapshotId: string }> => {
  return toCamel<{ status: string; snapshotId: string }>(await apiRequest(`/checkpoint/file-snapshot/${snapshotId}`, {
    method: 'DELETE',
  }));
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

  return toCamel<{ status: string; deleted: number; maxSnapshots: number }>(
    await apiRequest(`/checkpoint/file-snapshot/cleanup?${params.toString()}`, {
      method: 'POST',
    }),
  );
};
