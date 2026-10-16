/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 *
 * [OUTPUT]
 * getMemoryOrphanEstimate / startMemoryReindex / getMemoryReindexStatus: memories left behind by an embedding-model switch, and the background run that migrates them.
 * MemoryOrphanEstimate / MemoryReindexResult / MemoryReindexStatus: response DTOs.
 *
 * [POS]
 * Memory reindex client. `POST /memory/reindex` (202) starts the migration, or joins the one in flight for the same embedding model
 * (409 while a run into another model is in flight), and answers at once;
 * re-embedding goes through the user's embedding provider and takes minutes on a large store, so the caller polls
 * `GET /memory/reindex/status` until the run ends. Requests are silent: the Settings notice reports the outcome.
 */

import { apiRequest } from '@/lib/api';

export interface MemoryOrphanEstimate {
  total_memories: number;
  orphan_collections: { old_model_suffix: string }[];
}

/** Memories counted one by one: migrated now, already in place (or empty), or unable to migrate (retry later). */
export interface MemoryReindexResult {
  migrated: number;
  skipped: number;
  failed: number;
}

export interface MemoryReindexStatus {
  state: 'idle' | 'running' | 'succeeded' | 'failed';
  done: number;
  total: number;
  /** Present once the run has succeeded; `failed` can still be above zero. */
  result: MemoryReindexResult | null;
}

export const getMemoryOrphanEstimate = (): Promise<MemoryOrphanEstimate> =>
  apiRequest<MemoryOrphanEstimate>('/memory/reindex/estimate', { silent: true });

/** Starts the migration in the background, or joins the run already in flight; follow it with getMemoryReindexStatus. */
export const startMemoryReindex = (): Promise<MemoryReindexStatus> =>
  apiRequest<MemoryReindexStatus>('/memory/reindex', { method: 'POST', silent: true });

export const getMemoryReindexStatus = (): Promise<MemoryReindexStatus> =>
  apiRequest<MemoryReindexStatus>('/memory/reindex/status', { silent: true });
