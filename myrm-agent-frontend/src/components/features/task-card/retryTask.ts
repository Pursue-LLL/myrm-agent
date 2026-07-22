/**
 * [INPUT]
 * Browser fetch API (POS: Task retry request transport)
 *
 * [OUTPUT]
 * retryTask: Sends retry request and throws typed error on failure.
 * TaskRetryRequestError: Structured retry failure for UI rendering.
 *
 * [POS]
 * Task-card retry transport helper that normalizes API error payloads.
 */

type TaskRetryRecoverable = 'transient' | 'permanent';

interface TaskRetryErrorDetail {
  code: string;
  message: string;
  recoverable: TaskRetryRecoverable;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object') {
    return null;
  }
  return value as Record<string, unknown>;
}

function parseRecoverable(value: unknown): TaskRetryRecoverable | null {
  if (value === 'transient' || value === 'permanent') {
    return value;
  }
  return null;
}

function parseTaskRetryErrorDetail(value: unknown): TaskRetryErrorDetail | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }

  const code = typeof record.code === 'string' ? record.code : null;
  const message = typeof record.message === 'string' ? record.message : null;
  const recoverable = parseRecoverable(record.recoverable);
  if (!code || !message || !recoverable) {
    return null;
  }
  return { code, message, recoverable };
}

interface TaskRetryRequestErrorOptions {
  code: string;
  recoverable: TaskRetryRecoverable;
  status: number;
}

export class TaskRetryRequestError extends Error {
  readonly code: string;
  readonly recoverable: TaskRetryRecoverable;
  readonly status: number;

  constructor(message: string, options: TaskRetryRequestErrorOptions) {
    super(message);
    this.name = 'TaskRetryRequestError';
    this.code = options.code;
    this.recoverable = options.recoverable;
    this.status = options.status;
  }
}

async function readTaskRetryErrorDetail(response: Response): Promise<TaskRetryErrorDetail | null> {
  try {
    const bodyUnknown = (await response.json()) as unknown;
    const body = asRecord(bodyUnknown);
    if (!body) {
      return null;
    }
    return parseTaskRetryErrorDetail(body.detail);
  } catch {
    return null;
  }
}

export async function retryTask(taskId: string): Promise<void> {
  const response = await fetch(`/api/v1/tasks/${encodeURIComponent(taskId)}/retry`, { method: 'POST' });
  if (response.ok) {
    return;
  }

  const detail = await readTaskRetryErrorDetail(response);
  throw new TaskRetryRequestError(detail?.message ?? 'Unable to retry task right now. Please try again.', {
    code: detail?.code ?? 'TASK_RETRY_FAILED',
    recoverable: detail?.recoverable ?? 'permanent',
    status: response.status,
  });
}

