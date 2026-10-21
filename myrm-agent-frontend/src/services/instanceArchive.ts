/**
 * [INPUT]
 * - @/lib/api: apiRequest, fetchWithTimeout, ApiError (POS: authenticated backend client)
 * - @/lib/utils/authHeaders: getAuthHeaders (POS: Bearer header for raw fetch)
 * - @/lib/utils/fileUtils: triggerDownload (POS: shared save helper; system save dialog on desktop)
 * - @/lib/deploy-mode: isTauriRuntime
 *
 * [OUTPUT]
 * - Wire types of /instance-archive/* and `instanceArchiveService` (export jobs, resumable
 *   chunked upload, stage / confirm, one-time outcome, rollback)
 * - archiveErrorCode: stable machine-readable reason of a failed call
 *
 * [POS]
 * Frontend client of the instance backup API. Calls are silent: the UI maps the stable
 * `code` to localized copy instead of showing server wording.
 */

import { ApiError, apiRequest, fetchWithTimeout } from '@/lib/api';
import { isTauriRuntime } from '@/lib/deploy-mode';
import { getAuthHeaders } from '@/lib/utils/authHeaders';
import { triggerDownload } from '@/lib/utils/fileUtils';

const BASE = '/instance-archive';

/** Server cap is 8 MiB per chunk; 4 MiB keeps retries cheap on flaky links. */
export const UPLOAD_CHUNK_BYTES = 4 * 1024 * 1024;
const CHUNK_ATTEMPTS = 3;
const RESUME_STORAGE_KEY = 'myrm.instanceArchive.upload';
/** Statuses that signal a transient transport / proxy problem rather than a refused chunk. */
const RETRYABLE_STATUS: ReadonlySet<number> = new Set([408, 429, 502, 503, 504]);

export type RestartMode = 'sandbox' | 'process';
export type ExportState = 'running' | 'done' | 'failed' | 'cancelled';
export type ArchiveOperation = 'import' | 'restore_point' | 'rollback';

export interface ArchiveStatus {
  supported: boolean;
  can_protect_secrets: boolean;
  restart_mode: RestartMode;
  pending_operation: ArchiveOperation | null;
  rollback_available: boolean;
}

export interface ExportJob {
  job_id: string;
  state: ExportState;
  files_done: number;
  files_total: number;
  bytes_done: number;
  bytes_total: number;
  size_bytes: number | null;
  error_code: string | null;
  reentry: string[];
  config_key_carried: boolean;
  /** Carried items that exist but could not be read, so they are not in the file. */
  unreadable_count: number;
}

export interface UploadSession {
  session_id: string;
  size_bytes: number;
  chunk_bytes: number;
  chunk_count: number;
  received: number[];
  state: string;
}

export interface ImportReport {
  session_id: string;
  /** When the backup was made. */
  created_at: string;
  /** What the backup holds, and the same tables in the running app (empty when unreadable). */
  counts: Record<string, number>;
  current_counts: Record<string, number>;
  executable: Record<string, number>;
  reentry: string[];
  paused_jobs: number;
  missing_paths: number;
  /** Items the export could not read: the backup lacks them, so restoring removes the app's own copies. */
  unreadable_count: number;
  identity_dropped: boolean;
  config_key_carried: boolean;
}

export interface ArchiveOutcome {
  operation: ArchiveOperation;
  status: 'restored' | 'failed' | 'waiting';
  completed_at: string;
  summary: Record<string, number>;
  reentry: string[];
  error_code: string | null;
  rollback_available: boolean;
}

export interface QueuedSwap {
  operation: ArchiveOperation;
  requires_restart: boolean;
}

export interface UploadProgress {
  chunksDone: number;
  chunksTotal: number;
}

interface UploadOptions {
  signal?: AbortSignal;
  onProgress?: (progress: UploadProgress) => void;
}

interface ResumeRecord {
  fileKey: string;
  sessionId: string;
}

const silent = { silent: true } as const;
const jsonBody = (body: unknown): Pick<RequestInit, 'body'> => ({ body: JSON.stringify(body) });

/** Stable reason of a failed call: the server's `detail.code`, else `generic`. */
export function archiveErrorCode(error: unknown): string {
  if (error instanceof ApiError && error.businessCode) {
    return error.businessCode;
  }
  return 'generic';
}

const fileKey = (file: File): string => `${file.name}:${file.size}:${file.lastModified}`;

function readResume(): ResumeRecord | null {
  try {
    const raw = window.localStorage.getItem(RESUME_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as ResumeRecord) : null;
  } catch {
    return null;
  }
}

function writeResume(record: ResumeRecord | null): void {
  try {
    if (record) {
      window.localStorage.setItem(RESUME_STORAGE_KEY, JSON.stringify(record));
    } else {
      window.localStorage.removeItem(RESUME_STORAGE_KEY);
    }
  } catch {
    // Resuming after a reload is best effort; the in-memory upload is unaffected.
  }
}

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

export const instanceArchiveService = {
  getStatus: (): Promise<ArchiveStatus> => apiRequest<ArchiveStatus>(`${BASE}/status`, { method: 'GET', ...silent }),

  startExport: (passphrase?: string): Promise<ExportJob> =>
    apiRequest<ExportJob>(`${BASE}/exports`, {
      method: 'POST',
      ...jsonBody({ passphrase: passphrase || null }),
      ...silent,
    }),

  getExport: (jobId: string): Promise<ExportJob> =>
    apiRequest<ExportJob>(`${BASE}/exports/${jobId}`, { method: 'GET', ...silent }),

  discardExport: async (jobId: string): Promise<void> => {
    await apiRequest(`${BASE}/exports/${jobId}`, { method: 'DELETE', ...silent });
  },

  /** Streams to a user-chosen file where the browser allows it, otherwise buffers a Blob for the shared save helper. */
  async downloadExport(jobId: string, onBytes?: (received: number) => void): Promise<'saved' | 'cancelled'> {
    const suggestedName = `myrm-backup-${new Date().toISOString().slice(0, 16).replace(/[-:T]/g, '')}.zip`;
    const writable = await openSaveTarget(suggestedName);
    if (writable === 'cancelled') {
      return 'cancelled';
    }
    const response = await fetchWithTimeout(`${BASE}/exports/${jobId}/download`, { headers: getAuthHeaders() }, 0);
    if (!response.ok || !response.body) {
      await writable?.abort();
      throw new ApiError('Download failed', response.status, [], undefined, await responseCode(response));
    }
    const reader = response.body.getReader();
    const blobParts: BlobPart[] = [];
    let received = 0;
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        received += value.byteLength;
        onBytes?.(received);
        if (writable) {
          await writable.write(value);
        } else {
          blobParts.push(value as BlobPart);
        }
      }
    } catch (error) {
      await writable?.abort().catch(() => undefined);
      throw error;
    }
    if (writable) {
      await writable.close();
      return 'saved';
    }
    const saved = await triggerDownload(new Blob(blobParts, { type: 'application/zip' }), suggestedName);
    return saved ? 'saved' : 'cancelled';
  },

  /** Uploads in sequential chunks; the same file is resumed after a retry or a reload. */
  async uploadArchive(file: File, { signal, onProgress }: UploadOptions = {}): Promise<UploadSession> {
    let session = await resumeSession(file);
    if (!session) {
      session = await apiRequest<UploadSession>(`${BASE}/imports`, {
        method: 'POST',
        ...jsonBody({ size_bytes: file.size, chunk_bytes: UPLOAD_CHUNK_BYTES }),
        ...silent,
      });
      writeResume({ fileKey: fileKey(file), sessionId: session.session_id });
    }
    const received = new Set(session.received);
    onProgress?.({ chunksDone: received.size, chunksTotal: session.chunk_count });
    for (let index = 0; index < session.chunk_count; index += 1) {
      if (received.has(index)) {
        continue;
      }
      signal?.throwIfAborted();
      const start = index * session.chunk_bytes;
      session = await putChunk(session.session_id, index, file.slice(start, start + session.chunk_bytes), signal);
      received.add(index);
      onProgress?.({ chunksDone: received.size, chunksTotal: session.chunk_count });
    }
    return session;
  },

  stageImport: (sessionId: string, options: { passphrase?: string; skipSecrets?: boolean }): Promise<ImportReport> =>
    apiRequest<ImportReport>(`${BASE}/imports/${sessionId}/stage`, {
      method: 'POST',
      ...jsonBody({ passphrase: options.passphrase || null, skip_secrets: Boolean(options.skipSecrets) }),
      timeout: 15 * 60_000,
      ...silent,
    }),

  confirmImport: (sessionId: string, acknowledgeExecutables: boolean): Promise<QueuedSwap> =>
    apiRequest<QueuedSwap>(`${BASE}/imports/${sessionId}/confirm`, {
      method: 'POST',
      ...jsonBody({ acknowledge_executables: acknowledgeExecutables }),
      ...silent,
    }),

  cancelImport: async (sessionId: string): Promise<void> => {
    writeResume(null);
    await apiRequest(`${BASE}/imports/${sessionId}`, { method: 'DELETE', ...silent });
  },

  async getOutcome(): Promise<ArchiveOutcome | null> {
    const { outcome } = await apiRequest<{ outcome?: ArchiveOutcome | null }>(`${BASE}/outcome`, {
      method: 'GET',
      ...silent,
    });
    return outcome ?? null;
  },

  acknowledgeOutcome: async (): Promise<void> => {
    await apiRequest(`${BASE}/outcome/acknowledge`, { method: 'POST', ...silent });
  },

  queueRollback: (): Promise<QueuedSwap> => apiRequest<QueuedSwap>(`${BASE}/rollback`, { method: 'POST', ...silent }),
};

async function resumeSession(file: File): Promise<UploadSession | null> {
  const record = readResume();
  if (!record || record.fileKey !== fileKey(file)) {
    return null;
  }
  try {
    const session = await apiRequest<UploadSession>(`${BASE}/imports/${record.sessionId}`, {
      method: 'GET',
      ...silent,
    });
    return session.state === 'uploading' && session.size_bytes === file.size ? session : null;
  } catch {
    return null;
  }
}

async function putChunk(sessionId: string, index: number, data: Blob, signal?: AbortSignal): Promise<UploadSession> {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await apiRequest<UploadSession>(`${BASE}/imports/${sessionId}/chunks/${index}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/octet-stream' },
        body: data,
        signal,
        timeout: 120_000,
        ...silent,
      });
    } catch (error) {
      // A server answer is final (bad geometry, no space, closed session) unless it is a transient proxy status.
      const final = error instanceof ApiError && !RETRYABLE_STATUS.has(error.code);
      if (final || signal?.aborted || attempt >= CHUNK_ATTEMPTS) {
        throw error;
      }
      await sleep(400 * 2 ** attempt);
    }
  }
}

async function responseCode(response: Response): Promise<string | undefined> {
  try {
    const body = (await response.json()) as { detail?: { code?: string } };
    return body.detail?.code;
  } catch {
    return undefined;
  }
}

interface SaveTarget {
  write(chunk: Uint8Array): Promise<void>;
  close(): Promise<void>;
  abort(): Promise<void>;
}

interface SavePickerWindow {
  showSaveFilePicker?: (options: { suggestedName: string }) => Promise<{ createWritable(): Promise<SaveTarget> }>;
}

/**
 * The picker needs the click's user activation, so it opens before any network wait. The desktop
 * shell always saves through the shared helper's native dialog instead of the webview picker.
 */
async function openSaveTarget(suggestedName: string): Promise<SaveTarget | null | 'cancelled'> {
  const picker = (window as SavePickerWindow).showSaveFilePicker;
  if (!picker || isTauriRuntime()) {
    return null;
  }
  try {
    const handle = await picker.call(window, { suggestedName });
    return await handle.createWritable();
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return 'cancelled';
    }
    return null;
  }
}
