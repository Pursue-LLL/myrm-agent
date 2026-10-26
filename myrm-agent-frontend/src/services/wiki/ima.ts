/**
 * [INPUT]
 * @/lib/api::apiRequest (POS: frontend API request helper)
 * ./service::buildWikiApiPath (POS: Wiki API 路径构造)
 *
 * [OUTPUT]
 * ImaStatus / ImaLibrary / ImaItemView 等 DTO 与腾讯 ima 知识库导入的连接、选库、同步控制、编译与报告 API。
 * ImaItemBucket / ImaSyncPhase: 报告分桶与同步阶段取值。
 *
 * [POS]
 * ima 导入客户端。`/wiki/sources/ima/*` REST 契约：API Key 只写不读（任何响应都不回显），
 * 失败以 `{code, message}` 返回，界面按 `ApiError.businessCode` 映射用户可读文案，不展示服务端 message
 * （所有请求 `silent`，否则全局拦截器会把服务端英文 message 直接弹成 toast）。
 */

import { apiRequest } from '@/lib/api';
import { buildWikiApiPath } from './service';

export type ImaSyncPhase = 'idle' | 'inventory' | 'fetch';

export type ImaJobState = 'none' | 'active' | 'paused';

export type ImaItemBucket = 'attention' | 'lossy' | 'remote_deleted';

export interface ImaLibrary {
  id: string;
  name: string;
}

export interface ImaItemCounts {
  total: number;
  synced: number;
  pending: number;
  failed: number;
  unsupported: number;
  too_large: number;
  blocked: number;
  dismissed: number;
  remote_deleted: number;
  duplicate: number;
  /** Imported, but the content is a simplified version of the original. */
  partial: number;
}

/** A selected part of ima the last pass could not read completely; `name` is empty for the notes. */
export interface ImaUnreadable {
  kind: 'library' | 'notes';
  name: string;
}

export interface ImaStatus {
  connected: boolean;
  /** Masked client id, never the key. */
  account_hint: string;
  needs_reauth: boolean;
  knowledge_bases: ImaLibrary[];
  include_notes: boolean;
  /** `next_run_at` is only set while the next scheduled check is still ahead. */
  job: { state: ImaJobState; next_run_at: string | null };
  phase: ImaSyncPhase;
  backfill_complete: boolean;
  last_run_at: string | null;
  last_error_kind: string;
  unreadable: ImaUnreadable[];
  /** The Wiki-wide "auto-compile after sync" switch, which the ima import follows once its first import is done. */
  auto_compile: boolean;
  counts: ImaItemCounts;
  total_chars: number;
}

export interface ImaItemView {
  title: string;
  folder_path: string;
  container_name: string;
  media_kind: string;
  status: string;
  reason: string;
  notes: string[];
}

export interface ImaCredentialsInput {
  client_id: string;
  api_key: string;
}

export interface ImaSelectionInput {
  library_ids: string[];
  include_notes: boolean;
}

interface ImaCount {
  count: number;
}

/** Silent: the global handler would toast the server's English message; the card words every failure itself. */
function imaRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  return apiRequest<T>(path, { ...init, silent: true });
}

export function getImaStatus(agentId?: string | null): Promise<ImaStatus> {
  return imaRequest<ImaStatus>(buildWikiApiPath('/wiki/sources/ima', agentId));
}

export function saveImaCredentials(input: ImaCredentialsInput, agentId?: string | null): Promise<ImaStatus> {
  return imaRequest<ImaStatus>(buildWikiApiPath('/wiki/sources/ima/credentials', agentId), {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}

/** Removes the stored key and stops the sync; documents that were already imported stay in the wiki. */
export function deleteImaCredentials(agentId?: string | null): Promise<ImaStatus> {
  return imaRequest<ImaStatus>(buildWikiApiPath('/wiki/sources/ima/credentials', agentId), { method: 'DELETE' });
}

export function listImaLibraries(): Promise<ImaLibrary[]> {
  return imaRequest<ImaLibrary[]>('/wiki/sources/ima/libraries');
}

export function saveImaSelection(input: ImaSelectionInput, agentId?: string | null): Promise<ImaStatus> {
  return imaRequest<ImaStatus>(buildWikiApiPath('/wiki/sources/ima/config', agentId), {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}

export function startImaSync(locale: string, agentId?: string | null): Promise<ImaStatus> {
  return imaRequest<ImaStatus>(buildWikiApiPath('/wiki/sources/ima/sync/start', agentId), {
    method: 'POST',
    body: JSON.stringify({ locale }),
  });
}

export function pauseImaSync(agentId?: string | null): Promise<ImaStatus> {
  return imaRequest<ImaStatus>(buildWikiApiPath('/wiki/sources/ima/sync/pause', agentId), { method: 'POST' });
}

export function resumeImaSync(agentId?: string | null): Promise<ImaStatus> {
  return imaRequest<ImaStatus>(buildWikiApiPath('/wiki/sources/ima/sync/resume', agentId), { method: 'POST' });
}

/** Puts failed items back in the queue; resolves to how many were re-queued. */
export async function retryFailedImaItems(agentId?: string | null): Promise<number> {
  const result = await imaRequest<ImaCount>(buildWikiApiPath('/wiki/sources/ima/sync/retry-failed', agentId), {
    method: 'POST',
  });
  return result.count;
}

/** Queues only what ima imported (and that still needs compiling) for the knowledge build; resolves to the count. */
export async function compileImaImports(agentId?: string | null): Promise<number> {
  const result = await imaRequest<ImaCount>(buildWikiApiPath('/wiki/sources/ima/compile', agentId), {
    method: 'POST',
  });
  return result.count;
}

export function listImaItems(bucket: ImaItemBucket, agentId?: string | null): Promise<ImaItemView[]> {
  const params = new URLSearchParams({ bucket });
  return imaRequest<ImaItemView[]>(buildWikiApiPath(`/wiki/sources/ima/items?${params.toString()}`, agentId));
}
