import { apiRequest } from '@/lib/api';

export interface ArmAirbagResponse {
  success: boolean;
  taskId: string;
  baseSnapshotId?: string | null;
  isGitRepo: boolean;
  message?: string | null;
}

export interface AirbagStatusResponse {
  taskId: string;
  totalFilesChanged: number;
  modifiedFiles: string[];
  addedFiles: string[];
  deletedFiles: string[];
  externalEffects: string[];
  canRollback: boolean;
}

export interface RollbackAirbagResponse {
  success: boolean;
  taskId: string;
  status: 'rolled_back' | 'failed';
}

export interface DismissAirbagResponse {
  success: boolean;
  taskId: string;
  status: 'dismissed' | 'failed';
}

const snakeToCamelKey = (key: string): string => key.replace(/_([a-z0-9])/g, (_, ch: string) => ch.toUpperCase());

const toCamel = <T>(value: unknown): T => {
  if (Array.isArray(value)) {
    return value.map((item) => toCamel<unknown>(item)) as T;
  }
  if (value !== null && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => {
        return [snakeToCamelKey(k), toCamel<unknown>(v)];
      }),
    ) as T;
  }
  return value as T;
};

/**
 * Arm safety airbag before starting an unattended task
 */
export const armAirbag = async (taskId: string, workspacePath: string): Promise<ArmAirbagResponse> => {
  return toCamel<ArmAirbagResponse>(
    await apiRequest('/checkpoint/airbag/arm', {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId, workspace_path: workspacePath }),
    }),
  );
};

/**
 * Query cumulative status of an airbag
 */
export const getAirbagStatus = async (
  taskId: string,
  workspacePath?: string,
): Promise<AirbagStatusResponse> => {
  const params = new URLSearchParams();
  if (workspacePath) {
    params.append('workspace_path', workspacePath);
  }
  const query = params.toString();
  const url = `/checkpoint/airbag/${taskId}/status${query ? `?${query}` : ''}`;
  return toCamel<AirbagStatusResponse>(await apiRequest(url));
};

/**
 * Trigger time-travel rollback for a task
 */
export const rollbackAirbag = async (
  taskId: string,
  workspacePath?: string,
): Promise<RollbackAirbagResponse> => {
  return toCamel<RollbackAirbagResponse>(
    await apiRequest('/checkpoint/airbag/rollback', {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId, workspace_path: workspacePath }),
    }),
  );
};

/**
 * Dismiss airbag when user confirms changes are safe
 */
export const dismissAirbag = async (
  taskId: string,
  workspacePath?: string,
): Promise<DismissAirbagResponse> => {
  return toCamel<DismissAirbagResponse>(
    await apiRequest('/checkpoint/airbag/dismiss', {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId, workspace_path: workspacePath }),
    }),
  );
};
